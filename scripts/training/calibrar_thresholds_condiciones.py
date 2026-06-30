#!/usr/bin/env python3
"""Calibra thresholds de condition_mvp usando un benchmark fijo.

No reentrena pesos. Busca umbrales por condicion sobre un split de calibracion
y los evalua en un split holdout estable por `case_id`.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[2]
RUNTIME_MODEL = ROOT_DIR / "models/runtime/condition_mvp_model.pkl"
DEFAULT_DETAILS = ROOT_DIR / "data/reports/condition_model/09_nhanes_multi_cycle_benchmark_details.csv"
REPORT_DIR = ROOT_DIR / "data/reports/condition_model"
DEFAULT_REPORT = REPORT_DIR / "10_nhanes_multi_cycle_threshold_calibration.csv"
DEFAULT_SUMMARY = REPORT_DIR / "10_nhanes_multi_cycle_threshold_calibration_summary.csv"

sys.path.insert(0, str(ROOT_DIR))


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def split_bucket(case_id: str) -> str:
    digest = hashlib.sha256(case_id.encode("utf-8")).hexdigest()
    return "calibration" if int(digest[:8], 16) % 100 < 50 else "evaluation"


def parse_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "t", "yes", "si", "sí"}


def metrics_for_threshold(rows: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    tp = fp = tn = fn = 0
    for row in rows:
        expected_positive = row["expected_state"] == "positive"
        predicted_positive = float(row["probability"]) >= threshold
        if expected_positive and predicted_positive:
            tp += 1
        elif expected_positive and not predicted_positive:
            fn += 1
        elif not expected_positive and predicted_positive:
            fp += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    specificity = tn / (tn + fp) if (tn + fp) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    balanced_accuracy = (recall + specificity) / 2
    return {
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "specificity": round(specificity, 4),
        "f1": round(f1, 4),
        "balanced_accuracy": round(balanced_accuracy, 4),
    }


def choose_threshold(rows: list[dict[str, Any]], original_threshold: float, min_specificity: float) -> tuple[float, dict[str, Any], str]:
    positives = sum(1 for row in rows if row["expected_state"] == "positive")
    negatives = sum(1 for row in rows if row["expected_state"] == "negative")
    original_metrics = metrics_for_threshold(rows, original_threshold)
    if positives < 10 or negatives < 10:
        return original_threshold, original_metrics, "insufficient_calibration_labels"

    candidates = [round(i / 100, 2) for i in range(1, 100)]
    scored = []
    for threshold in candidates:
        metric = metrics_for_threshold(rows, threshold)
        if metric["specificity"] >= min_specificity:
            scored.append((threshold, metric))
    if not scored:
        return original_threshold, original_metrics, "no_threshold_meets_specificity_floor"

    scored.sort(key=lambda item: (item[1]["f1"], item[1]["recall"], item[1]["specificity"]), reverse=True)
    best_threshold, best_metrics = scored[0]
    if best_metrics["f1"] <= original_metrics["f1"]:
        return original_threshold, original_metrics, "original_threshold_not_worse"
    return best_threshold, best_metrics, "candidate"


def load_details(path: Path, min_confidence: float) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = []
        for row in csv.DictReader(handle):
            if row["expected_state"] not in {"positive", "negative"}:
                continue
            if str(row.get("evaluated", "")).lower() not in {"true", "1"}:
                continue
            if float(row.get("confidence", 0)) < min_confidence:
                continue
            row["probability"] = float(row["probability"])
            row["threshold"] = float(row["threshold"])
            row["split"] = split_bucket(row["case_id"])
            rows.append(row)
    return rows


def run(args: argparse.Namespace) -> None:
    generated_at = utc_now()
    details_path = Path(args.details)
    report_path = Path(args.report)
    summary_path = Path(args.summary)
    rows = load_details(details_path, min_confidence=args.min_confidence)
    if not rows:
        raise SystemExit(f"No hay filas evaluables para calibrar en {details_path}")

    by_condition: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_condition.setdefault(row["condition"], []).append(row)

    report_rows = []
    accepted_thresholds: dict[str, float] = {}
    for condition, condition_rows in sorted(by_condition.items()):
        calibration_rows = [row for row in condition_rows if row["split"] == "calibration"]
        evaluation_rows = [row for row in condition_rows if row["split"] == "evaluation"]
        if not calibration_rows or not evaluation_rows:
            continue
        original_threshold = float(calibration_rows[0]["threshold"])
        min_specificity = args.safety_min_specificity if condition.startswith("SAFETY_") else args.min_specificity_floor
        candidate_threshold, calibration_metric, status = choose_threshold(
            calibration_rows,
            original_threshold=original_threshold,
            min_specificity=min_specificity,
        )
        original_eval = metrics_for_threshold(evaluation_rows, original_threshold)
        candidate_eval = metrics_for_threshold(evaluation_rows, candidate_threshold)
        accepted = (
            status == "candidate"
            and candidate_eval["f1"] >= original_eval["f1"]
            and candidate_eval["specificity"] >= max(args.min_specificity_floor, original_eval["specificity"] - 0.02)
            and candidate_threshold >= args.min_accepted_threshold
        )
        if accepted:
            accepted_thresholds[condition] = candidate_threshold
        report_rows.append(
            {
                "generated_at": generated_at,
                "condition": condition,
                "calibration_rows": len(calibration_rows),
                "evaluation_rows": len(evaluation_rows),
                "original_threshold": original_threshold,
                "candidate_threshold": candidate_threshold,
                "status": status,
                "accepted_for_model": accepted,
                "calibration_f1": calibration_metric["f1"],
                "calibration_recall": calibration_metric["recall"],
                "calibration_specificity": calibration_metric["specificity"],
                "original_eval_f1": original_eval["f1"],
                "original_eval_recall": original_eval["recall"],
                "original_eval_specificity": original_eval["specificity"],
                "candidate_eval_f1": candidate_eval["f1"],
                "candidate_eval_recall": candidate_eval["recall"],
                "candidate_eval_specificity": candidate_eval["specificity"],
                "eval_tp": candidate_eval["tp"],
                "eval_fp": candidate_eval["fp"],
                "eval_tn": candidate_eval["tn"],
                "eval_fn": candidate_eval["fn"],
            }
        )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(report_rows).to_csv(report_path, index=False)
    pd.DataFrame(
        [
            {
                "generated_at": generated_at,
                "details_path": str(details_path),
                "conditions_seen": len(report_rows),
                "accepted_thresholds": len(accepted_thresholds),
                "accepted_conditions": "|".join(sorted(accepted_thresholds)),
                "apply_requested": args.apply,
                "model_path": str(RUNTIME_MODEL),
                "clinical_validation": "threshold_calibration_not_diagnosis",
            }
        ]
    ).to_csv(summary_path, index=False)

    if args.apply and accepted_thresholds:
        artifact = joblib.load(RUNTIME_MODEL)
        thresholds = dict(artifact.get("thresholds", {}))
        backup_path = RUNTIME_MODEL.with_suffix(f".{generated_at.replace(':', '').replace('+', '_')}.bak.pkl")
        shutil.copy2(RUNTIME_MODEL, backup_path)
        thresholds.update(accepted_thresholds)
        artifact["thresholds"] = thresholds
        artifact["threshold_calibration"] = {
            "generated_at": generated_at,
            "source": str(details_path),
            "accepted_thresholds": accepted_thresholds,
            "backup_path": str(backup_path),
        }
        joblib.dump(artifact, RUNTIME_MODEL)

    print("Calibracion de thresholds condition_mvp completada")
    print(f"  condiciones evaluadas: {len(report_rows)}")
    print(f"  thresholds aceptados: {len(accepted_thresholds)}")
    print(f"  reporte: {report_path}")
    if args.apply:
        print("  apply: ejecutado" if accepted_thresholds else "  apply: sin cambios aceptados")


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibra thresholds condition_mvp con benchmark NHANES.")
    parser.add_argument("--details", default=str(DEFAULT_DETAILS), help="CSV detalle benchmark.")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="CSV de calibracion.")
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY), help="CSV resumen.")
    parser.add_argument("--min-confidence", type=float, default=0.75, help="Confianza minima de labels.")
    parser.add_argument("--min-specificity-floor", type=float, default=0.85, help="Specificity minima para condiciones no safety.")
    parser.add_argument("--safety-min-specificity", type=float, default=0.95, help="Specificity minima para condiciones safety.")
    parser.add_argument("--min-accepted-threshold", type=float, default=0.05, help="No aplica thresholds menores a este valor.")
    parser.add_argument("--apply", action="store_true", help="Actualiza thresholds aceptados en el artefacto del modelo.")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
