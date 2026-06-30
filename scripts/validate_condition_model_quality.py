#!/usr/bin/env python3
"""Valida calidad operativa del Modelo 1 de condiciones.

Este gate no reentrena. Usa benchmarks fijos ya generados:
- golden cases de regresion funcional;
- benchmark NHANES multi-ciclo por condicion y por fuerza de evidencia.

Falla solo con regresiones duras. Las condiciones blandas pueden quedar como
`necesita_mejora`, pero se reportan de forma visible para calibracion futura.
"""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT_DIR / "data/reports/condition_model"
GOLDEN_SUMMARY = REPORT_DIR / "05_golden_summary.csv"
CONDITION_METRICS = REPORT_DIR / "09_nhanes_multi_cycle_benchmark_condition_metrics.csv"
EVIDENCE_METRICS = REPORT_DIR / "09_nhanes_multi_cycle_benchmark_evidence_group_metrics.csv"
EXECUTIVE_REPORT = REPORT_DIR / "09_nhanes_multi_cycle_benchmark_executive_report.csv"

SAFETY_CONDITIONS = {"SAFETY_RENAL", "SAFETY_HEPATICA", "SAFETY_TIROIDEA"}
SOFT_CONDITIONS = {
    "BAJA_INMUNIDAD",
    "ESTRES_SUENO",
    "RENDIMIENTO_DEPORTIVO",
    "RIESGO_CABELLO_PIEL_UNAS",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise SystemExit(f"Falta reporte requerido: {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def as_float(value: Any, default: float | None = None) -> float | None:
    if value in {"", None}:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def run_golden() -> dict[str, str]:
    subprocess.run(
        [
            sys.executable,
            "scripts/training/evaluar_casos_golden_condiciones.py",
            "--fail-on-case-failure",
        ],
        cwd=ROOT_DIR,
        check=True,
    )
    rows = read_csv(GOLDEN_SUMMARY)
    if not rows:
        raise SystemExit("Golden summary vacio.")
    return rows[0]


def main() -> None:
    errors: list[str] = []
    warnings: list[str] = []

    golden = run_golden()
    case_pass_rate = as_float(golden.get("case_pass_rate"), 0.0) or 0.0
    if case_pass_rate < 1.0:
        errors.append(f"golden_case_pass_rate_below_1:{case_pass_rate}")

    condition_rows = read_csv(CONDITION_METRICS)
    evidence_rows = read_csv(EVIDENCE_METRICS)
    executive_rows = read_csv(EXECUTIVE_REPORT)

    by_condition = {row["condition"]: row for row in condition_rows}
    for condition in SAFETY_CONDITIONS:
        row = by_condition.get(condition)
        recall = as_float(row.get("recall") if row else None)
        coverage = as_float(row.get("coverage") if row else None, 0.0) or 0.0
        if coverage >= 0.10 and recall is not None and recall < 0.95:
            errors.append(f"safety_recall_below_0_95:{condition}:{recall}")

    for row in executive_rows:
        condition = row["condition"]
        status = row.get("status", "")
        false_negative_risk = row.get("false_negative_risk", "")
        if condition in SOFT_CONDITIONS and status == "no_evaluable":
            warnings.append(f"soft_condition_not_evaluable:{condition}")
        elif status == "necesita_mejora" or false_negative_risk in {"medio", "alto"}:
            warnings.append(f"condition_needs_improvement:{condition}:{false_negative_risk}")

    evidence_groups = sorted({row["evidence_group"] for row in evidence_rows if row.get("evidence_group")})
    required_groups = {"lab_only", "diet_only", "safety_only"}
    missing_groups = sorted(required_groups - set(evidence_groups))
    if missing_groups:
        errors.append(f"missing_evidence_groups:{'|'.join(missing_groups)}")

    summary = {
        "status": "failed" if errors else "passed",
        "errors": errors,
        "warnings": warnings,
        "golden_cases": int(golden.get("total_cases", 0)),
        "golden_pass_rate": case_pass_rate,
        "conditions_reported": len(condition_rows),
        "evidence_groups": evidence_groups,
        "reports": {
            "golden_summary": str(GOLDEN_SUMMARY),
            "condition_metrics": str(CONDITION_METRICS),
            "evidence_metrics": str(EVIDENCE_METRICS),
            "executive_report": str(EXECUTIVE_REPORT),
        },
    }
    print(summary)
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
