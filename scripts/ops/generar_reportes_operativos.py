from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT_DIR / "data/reports/operational"


def run_command(name: str, command: list[str], *, required: bool) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    result = subprocess.run(
        command,
        cwd=ROOT_DIR,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    finished = datetime.now(timezone.utc)
    output_path = REPORT_DIR / f"{name}.log"
    output_path.write_text(result.stdout, encoding="utf-8")
    return {
        "name": name,
        "command": command,
        "required": required,
        "status": "passed" if result.returncode == 0 else "failed",
        "returncode": result.returncode,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_seconds": round((finished - started).total_seconds(), 2),
        "log_path": str(output_path),
    }


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def build_catalog_command(args: argparse.Namespace) -> list[str]:
    report_path = ROOT_DIR / "data/reports/scraping/catalog_pipeline_current_report.json"
    return [
        sys.executable,
        "scripts/validation/validar_pipeline_catalogo.py",
        "--raw",
        str(args.raw_catalog),
        "--approved",
        str(args.approved_catalog),
        "--rejects",
        str(args.rejects),
        "--report-out",
        str(report_path),
        "--mode",
        args.catalog_mode,
        "--min-raw-rows",
        str(args.min_raw_rows),
        "--min-approved-rows",
        str(args.min_approved_rows),
        "--min-pharmacies",
        str(args.min_pharmacies),
        "--max-raw-age-hours",
        str(args.max_raw_age_hours),
    ]


def status_from_report(report: dict[str, Any] | None, key: str = "status") -> str:
    if not report:
        return "missing"
    return str(report.get(key) or "unknown")


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera reportes operativos para /health/ops y staging.")
    parser.add_argument("--strict", action="store_true", help="Falla si cualquier validación requerida falla.")
    parser.add_argument("--skip-condition", action="store_true", help="Omite benchmark del modelo de condiciones.")
    parser.add_argument("--skip-catalog", action="store_true", help="Omite validación de scraping/catálogo.")
    parser.add_argument("--catalog-mode", default=os.environ.get("CATALOG_VALIDATION_MODE", "weekly"))
    parser.add_argument("--raw-catalog", type=Path, default=Path("data/raw/pharmacies/supplements_exhaustive_clean.csv"))
    parser.add_argument("--approved-catalog", type=Path, default=Path("data/catalog/approved_catalog.csv"))
    parser.add_argument("--rejects", type=Path, default=Path("data/reports/scraping/supplements_rejected.csv"))
    parser.add_argument("--min-raw-rows", type=int, default=int(os.environ.get("CATALOG_MIN_RAW_ROWS", "500")))
    parser.add_argument("--min-approved-rows", type=int, default=int(os.environ.get("CATALOG_MIN_APPROVED_ROWS", "250")))
    parser.add_argument("--min-pharmacies", type=int, default=int(os.environ.get("CATALOG_MIN_PHARMACIES", "3")))
    parser.add_argument("--max-raw-age-hours", type=int, default=int(os.environ.get("CATALOG_MAX_RAW_AGE_HOURS", "168")))
    args = parser.parse_args()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    commands: list[tuple[str, list[str], bool]] = [
        ("model2_quality", [sys.executable, "scripts/validate_model2_quality.py"], True),
        ("commercial_engine_quality", [sys.executable, "scripts/validate_commercial_engine_quality.py"], True),
        ("lab_ocr_quality", [sys.executable, "scripts/validate_lab_ocr_quality.py"], True),
    ]
    if not args.skip_condition:
        commands.append(("condition_model_quality", [sys.executable, "scripts/validate_condition_model_quality.py"], False))
    if not args.skip_catalog:
        commands.append(("catalog_pipeline_quality", build_catalog_command(args), False))

    results = [run_command(name, command, required=required) for name, command, required in commands]

    model2 = read_json(ROOT_DIR / "data/reports/supplement_model/01_model2_summary.json")
    commercial = read_json(ROOT_DIR / "data/reports/commercial_engine/01_commercial_engine_summary.json")
    ocr = read_json(ROOT_DIR / "data/reports/labs/01_ocr_lab_summary.json")
    catalog = read_json(ROOT_DIR / "data/reports/scraping/catalog_pipeline_current_report.json")

    failed_required = [result["name"] for result in results if result["required"] and result["status"] != "passed"]
    failed_optional = [result["name"] for result in results if not result["required"] and result["status"] != "passed"]
    summary = {
        "status": "failed" if failed_required else ("attention" if failed_optional else "passed"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "tesseract_available": shutil.which("tesseract") is not None,
        "failed_required": failed_required,
        "failed_optional": failed_optional,
        "results": results,
        "reports": {
            "model2_quality": {
                "status": status_from_report(model2),
                "path": "data/reports/supplement_model/01_model2_summary.json",
            },
            "commercial_engine_quality": {
                "status": status_from_report(commercial),
                "path": "data/reports/commercial_engine/01_commercial_engine_summary.json",
            },
            "lab_ocr_quality": {
                "status": status_from_report(ocr),
                "path": "data/reports/labs/01_ocr_lab_summary.json",
            },
            "catalog_pipeline_quality": {
                "status": status_from_report(catalog),
                "path": "data/reports/scraping/catalog_pipeline_current_report.json",
            },
        },
    }
    out_path = REPORT_DIR / "quality_summary.json"
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if args.strict and summary["status"] == "failed":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
