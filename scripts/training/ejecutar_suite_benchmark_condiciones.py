#!/usr/bin/env python3
"""Ejecuta la suite completa condition_mvp + benchmark NHANES.

Flujo:
1. Opcionalmente reentrena condition_mvp.
2. Importa NHANES multi-ciclo y genera predicciones.
3. Construye benchmark semi-curado.
4. Calibra thresholds contra split fijo.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
PYTHON = sys.executable


def run_step(name: str, command: list[str]) -> None:
    print(f"\n== {name} ==")
    print(" ".join(command))
    subprocess.run(command, cwd=ROOT_DIR, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Corre entrenamiento y benchmark condition_mvp.")
    parser.add_argument("--skip-train", action="store_true", help="No reentrena el modelo.")
    parser.add_argument("--rows", type=int, default=10_000, help="Filas semisinteticas para entrenamiento.")
    parser.add_argument("--seed", type=int, default=42, help="Semilla de entrenamiento.")
    parser.add_argument("--limit-per-cycle", type=int, default=500, help="Casos adultos NHANES por ciclo.")
    parser.add_argument("--apply-calibration", action="store_true", help="Aplica thresholds aceptados al modelo.")
    args = parser.parse_args()

    if not args.skip_train:
        run_step(
            "Entrenar condition_mvp",
            [
                PYTHON,
                "scripts/training/entrenar_modelo_condiciones.py",
                "--rows",
                str(args.rows),
                "--seed",
                str(args.seed),
            ],
        )

    run_step(
        "Importar NHANES multi-ciclo",
        [
            PYTHON,
            "scripts/training/importar_casos_nhanes_multiciclo.py",
            "--limit-per-cycle",
            str(args.limit_per_cycle),
        ],
    )

    run_step(
        "Construir benchmark NHANES multi-ciclo",
        [
            PYTHON,
            "scripts/training/construir_benchmark_nhanes_condiciones.py",
            "--cases",
            "data/evaluation/condition_model/real_cases/nhanes_multi_cycle_condition_cases.csv",
            "--predictions",
            "data/reports/condition_model/08_nhanes_multi_cycle_predictions.csv",
            "--labels",
            "data/evaluation/condition_model/nhanes_multi_cycle_benchmark_labels.csv",
            "--details",
            "data/reports/condition_model/09_nhanes_multi_cycle_benchmark_details.csv",
            "--case-results",
            "data/reports/condition_model/09_nhanes_multi_cycle_benchmark_case_results.csv",
            "--condition-metrics",
            "data/reports/condition_model/09_nhanes_multi_cycle_benchmark_condition_metrics.csv",
            "--evidence-metrics",
            "data/reports/condition_model/09_nhanes_multi_cycle_benchmark_evidence_group_metrics.csv",
            "--executive-report",
            "data/reports/condition_model/09_nhanes_multi_cycle_benchmark_executive_report.csv",
            "--summary",
            "data/reports/condition_model/09_nhanes_multi_cycle_benchmark_summary.csv",
        ],
    )

    calibration_command = [
        PYTHON,
        "scripts/training/calibrar_thresholds_condiciones.py",
    ]
    if args.apply_calibration:
        calibration_command.append("--apply")
    run_step("Calibrar thresholds", calibration_command)

    print("\nSuite condition_mvp benchmark completada.")
    print("Resumen: data/reports/condition_model/09_nhanes_multi_cycle_benchmark_summary.csv")
    print("Reporte ejecutivo: data/reports/condition_model/09_nhanes_multi_cycle_benchmark_executive_report.csv")


if __name__ == "__main__":
    main()
