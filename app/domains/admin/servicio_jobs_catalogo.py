from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.core.config import BASE_DIR
from app.db.models import CatalogJob, utcnow
from app.db.session import SessionLocal


REPORT_DIR = BASE_DIR / "data/reports/scraping"
STATE_PATH = REPORT_DIR / "catalog_admin_job_state.json"


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _pid_running(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def catalog_job_status() -> dict[str, Any]:
    state = _read_json(STATE_PATH) or {}
    pid = state.get("pid")
    try:
        pid_int = int(pid) if pid is not None else None
    except (TypeError, ValueError):
        pid_int = None
    running = state.get("status") == "running" and _pid_running(pid_int)
    if state.get("status") == "running" and not running:
        state = {**state, "status": "unknown_finished", "running": False}

    current_report = _read_json(REPORT_DIR / "catalog_pipeline_current_report.json")
    alert_report = _read_json(REPORT_DIR / "catalog_pipeline_alert.json")
    diff_report = _read_json(REPORT_DIR / "catalog_diff_current.json")
    with SessionLocal() as db:
        latest_jobs = list(
            db.scalars(select(CatalogJob).order_by(CatalogJob.created_at.desc()).limit(10))
        )
        latest_job = latest_jobs[0] if latest_jobs else None
    return {
        "running": running,
        "state": state or None,
        "current_report": current_report,
        "alert": alert_report,
        "diff": diff_report,
        "latest_job": _job_out(latest_job) if latest_job else None,
        "jobs": [_job_out(job) for job in latest_jobs],
    }


def _job_out(job: CatalogJob | None) -> dict[str, Any] | None:
    if job is None:
        return None
    return {
        "id": str(job.id),
        "mode": job.mode,
        "status": job.status,
        "pid": job.pid,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "approved_at": job.approved_at.isoformat() if job.approved_at else None,
        "cancel_requested_at": job.cancel_requested_at.isoformat() if job.cancel_requested_at else None,
        "returncode": job.returncode,
        "log_path": job.log_path,
        "requested_params": job.requested_params_json or {},
        "result": job.result_json or {},
        "diff": job.diff_json or {},
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


def start_catalog_job(
    *,
    mode: str,
    limit_per_pharmacy: int,
    pharmacies: list[str],
    max_raw_age_hours: int,
    import_to_postgres: bool,
    requested_by: str,
) -> dict[str, Any]:
    status = catalog_job_status()
    if status["running"]:
        return {
            "accepted": False,
            "message": "Ya hay una actualización de catálogo en ejecución.",
            "status": status,
        }

    with SessionLocal() as db:
        job = CatalogJob(
            requested_by_user_id=UUID(requested_by),
            mode=mode,
            status="queued",
            requested_params_json={
                "mode": mode,
                "limit_per_pharmacy": limit_per_pharmacy,
                "pharmacies": pharmacies,
                "max_raw_age_hours": max_raw_age_hours,
                "import_to_postgres": import_to_postgres,
            },
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = job.id

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "scripts/ops/ejecutar_job_catalogo_admin.py",
        "--mode",
        mode,
        "--limit-per-pharmacy",
        str(limit_per_pharmacy),
        "--max-raw-age-hours",
        str(max_raw_age_hours),
        "--requested-by",
        requested_by,
        "--catalog-job-id",
        str(job_id),
    ]
    if pharmacies:
        command.extend(["--pharmacies", ",".join(pharmacies)])
    if import_to_postgres:
        command.append("--import-to-postgres")

    process = subprocess.Popen(
        command,
        cwd=BASE_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    state = {
        "status": "running",
        "mode": mode,
        "pid": process.pid,
        "catalog_job_id": str(job_id),
        "requested_by": requested_by,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "returncode": None,
        "state_path": str(STATE_PATH),
    }
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with SessionLocal() as db:
        job = db.get(CatalogJob, job_id)
        if job is not None:
            job.status = "running"
            job.pid = process.pid
            job.started_at = utcnow()
            job.updated_at = utcnow()
            db.commit()
    return {
        "accepted": True,
        "message": "Actualización de catálogo iniciada en background.",
        "job_id": str(job_id),
        "status": catalog_job_status(),
    }


def cancel_catalog_job(*, job_id: str | None, cancelled_by: str) -> dict[str, Any]:
    with SessionLocal() as db:
        job = db.get(CatalogJob, UUID(job_id)) if job_id else db.scalar(
            select(CatalogJob)
            .where(CatalogJob.status.in_(["queued", "running"]))
            .order_by(CatalogJob.created_at.desc())
            .limit(1)
        )
        if job is None:
            return {"cancelled": False, "message": "No hay job activo para cancelar.", "status": catalog_job_status()}
        if job.status not in {"queued", "running"}:
            return {"cancelled": False, "message": "El job ya no está activo.", "status": catalog_job_status()}
        pid = job.pid
        killed = False
        if pid:
            try:
                os.killpg(pid, signal.SIGTERM)
                killed = True
            except OSError:
                try:
                    os.kill(pid, signal.SIGTERM)
                    killed = True
                except OSError:
                    killed = False
        job.status = "cancelled"
        job.cancel_requested_at = utcnow()
        job.cancelled_by_user_id = UUID(cancelled_by)
        job.finished_at = utcnow()
        job.error_message = "Cancelado por admin"
        job.updated_at = utcnow()
        db.commit()
    state = _read_json(STATE_PATH) or {}
    state.update({"status": "cancelled", "finished_at": datetime.now(timezone.utc).isoformat()})
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"cancelled": True, "message": "Job cancelado." if killed else "Job marcado como cancelado.", "status": catalog_job_status()}


def approve_catalog_import(*, job_id: str, approved_by: str) -> dict[str, Any]:
    with SessionLocal() as db:
        job = db.get(CatalogJob, UUID(job_id))
        if job is None:
            return {"approved": False, "message": "Job no encontrado.", "status": catalog_job_status()}
        if job.mode != "update_prices":
            return {
                "approved": False,
                "message": "Solo los jobs de reconstrucción de catálogo pueden importarse.",
                "status": catalog_job_status(),
            }
        if job.status not in {"completed", "import_failed"}:
            return {"approved": False, "message": "Solo se puede aprobar un job completado.", "status": catalog_job_status()}
        validation = (job.result_json or {}).get("catalog_validation") or {}
        if validation.get("status") != "passed":
            return {"approved": False, "message": "La validación del catálogo no pasó.", "status": catalog_job_status()}

    import_process = subprocess.run(
        [sys.executable, "scripts/catalog/importar_catalogo_postgres.py", "--catalog", "data/catalog/approved_catalog.csv"],
        cwd=BASE_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    snapshot_process = subprocess.run(
        [
            sys.executable,
            "scripts/catalog/guardar_snapshots_precios.py",
            "--catalog",
            "data/catalog/approved_catalog.csv",
            "--catalog-job-id",
            job_id,
        ],
        cwd=BASE_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )

    result = {
        "import_returncode": import_process.returncode,
        "import_output": import_process.stdout[-4000:],
        "snapshot_returncode": snapshot_process.returncode,
        "snapshot_output": snapshot_process.stdout[-4000:],
    }
    success = import_process.returncode == 0 and snapshot_process.returncode == 0
    with SessionLocal() as db:
        job = db.get(CatalogJob, UUID(job_id))
        if job is not None:
            job.status = "approved_imported" if success else "import_failed"
            job.approved_by_user_id = UUID(approved_by)
            job.approved_at = utcnow() if success else None
            job.result_json = {**(job.result_json or {}), "approval": result}
            job.error_message = None if success else "Falló importación o snapshots"
            job.updated_at = utcnow()
            db.commit()
    return {
        "approved": success,
        "message": "Catálogo importado y snapshots guardados." if success else "Falló la importación aprobada.",
        "result": result,
        "status": catalog_job_status(),
    }
