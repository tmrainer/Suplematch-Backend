from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID


ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from app.db.models import CatalogJob, utcnow
from app.db.session import SessionLocal

REPORT_DIR = ROOT_DIR / "data/reports/scraping"
STATE_PATH = REPORT_DIR / "catalog_admin_job_state.json"
DIFF_PATH = REPORT_DIR / "catalog_diff_current.json"


def write_state(payload: dict) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in (REPORT_DIR / "catalog_pipeline_current_report.json", DIFF_PATH):
        try:
            stale.unlink()
        except FileNotFoundError:
            pass
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    STATE_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def update_job(job_id: UUID | None, **values) -> None:
    if job_id is None:
        return
    with SessionLocal() as db:
        job = db.get(CatalogJob, job_id)
        if job is None:
            return
        for key, value in values.items():
            setattr(job, key, value)
        job.updated_at = utcnow()
        db.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description="Ejecuta actualización de catálogo solicitada por admin.")
    parser.add_argument("--mode", choices=["validate_only", "price_only", "update_prices"], required=True)
    parser.add_argument("--limit-per-pharmacy", type=int, default=1000)
    parser.add_argument("--pharmacies", default="")
    parser.add_argument("--max-raw-age-hours", type=int, default=168)
    parser.add_argument("--import-to-postgres", action="store_true")
    parser.add_argument("--requested-by", default="")
    parser.add_argument("--catalog-job-id", default="")
    args = parser.parse_args()

    started_at = datetime.now(timezone.utc).isoformat()
    log_path = REPORT_DIR / f"catalog_admin_{args.mode}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.log"
    job_id = UUID(args.catalog_job_id) if args.catalog_job_id else None
    env = os.environ.copy()
    env.update(
        {
            "RUN_LABEL": "admin_manual",
            "LOCK_NAME": "catalog_update",
            "VALIDATION_MODE": "weekly",
            "MAX_RAW_AGE_HOURS": str(args.max_raw_age_hours),
            "LIMIT_PER_PHARMACY": str(args.limit_per_pharmacy),
            "IMPORT_TO_POSTGRES": "1" if args.import_to_postgres else "0",
            "ENRICH_CATALOG_FLAGS": "1",
        }
    )
    if args.mode == "validate_only":
        env["VALIDATE_ONLY"] = "1"
    if args.pharmacies:
        env["SCRAPER_PHARMACIES"] = args.pharmacies

    state = {
        "status": "running",
        "mode": args.mode,
        "pid": os.getpid(),
        "catalog_job_id": str(job_id) if job_id else None,
        "requested_by": args.requested_by or None,
        "started_at": started_at,
        "finished_at": None,
        "returncode": None,
        "log_path": str(log_path),
        "state_path": str(STATE_PATH),
    }
    write_state(state)
    update_job(
        job_id,
        status="running",
        pid=os.getpid(),
        started_at=utcnow(),
        log_path=str(log_path),
    )

    diff_catalog_path = Path("data/catalog/approved_catalog.csv")
    if args.mode == "price_only":
        price_snapshot_path = REPORT_DIR / "catalog_admin_price_snapshot.csv"
        rejects_path = REPORT_DIR / "catalog_admin_price_rejected.csv"
        scraper_command = [
            sys.executable,
            "scripts/scraping/scraper_suplementos.py",
            "--limit-per-pharmacy",
            str(args.limit_per_pharmacy),
            "--delay",
            os.environ.get("SCRAPER_DELAY", "0.25"),
            "--infer-registro",
            "--out",
            str(price_snapshot_path),
            "--rejects-out",
            str(rejects_path),
        ]
        if args.pharmacies:
            for pharmacy in args.pharmacies.split(","):
                clean_pharmacy = pharmacy.strip()
                if clean_pharmacy:
                    scraper_command.extend(["--pharmacy", clean_pharmacy])
        with log_path.open("w", encoding="utf-8") as log_handle:
            process = subprocess.run(
                scraper_command,
                cwd=ROOT_DIR,
                env=env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                check=False,
                text=True,
            )
        diff_catalog_path = price_snapshot_path
    else:
        with log_path.open("w", encoding="utf-8") as log_handle:
            process = subprocess.run(
                ["bash", "scripts/scraping/run_weekly_supplement_update.sh"],
                cwd=ROOT_DIR,
                env=env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                check=False,
                text=True,
            )

    diff_payload: dict = {}
    diff_process = subprocess.run(
        [
            sys.executable,
            "scripts/catalog/generar_diff_catalogo.py",
            "--catalog",
            str(diff_catalog_path),
            "--rejects",
            "data/reports/scraping/supplements_rejected.csv",
            "--out",
            str(DIFF_PATH),
        ],
        cwd=ROOT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    with log_path.open("a", encoding="utf-8") as log_handle:
        log_handle.write("\n== catalog diff ==\n")
        log_handle.write(diff_process.stdout)
    diff_payload = read_json(DIFF_PATH)
    report_payload = read_json(REPORT_DIR / "catalog_pipeline_current_report.json")
    result_payload = {
        "catalog_validation": report_payload if report_payload else {"status": "missing"},
        "diff_generated": bool(diff_payload),
        "diff_returncode": diff_process.returncode,
    }
    state.update(
        {
            "status": "completed" if process.returncode == 0 else "failed",
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "returncode": process.returncode,
            "diff_path": str(DIFF_PATH),
        }
    )
    write_state(state)
    update_job(
        job_id,
        status="completed" if process.returncode == 0 else "failed",
        finished_at=utcnow(),
        returncode=process.returncode,
        result_json=result_payload,
        diff_json=diff_payload,
        error_message=None if process.returncode == 0 else "; ".join(report_payload.get("errors") or []) or "catalog_job_failed",
    )
    return process.returncode


if __name__ == "__main__":
    raise SystemExit(main())
