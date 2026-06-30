#!/usr/bin/env python3
"""Evalua condition_mvp contra un holdout semisintetico nuevo.

Este script no reentrena. Genera casos no vistos con otra semilla, usa las
reglas curadas como referencia y compara contra el modelo entrenado actual.
"""

from __future__ import annotations

import argparse
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import f1_score, hamming_loss, precision_score, recall_score


ROOT_DIR = Path(__file__).resolve().parents[2]
TRAINING_SCRIPT_DIR = ROOT_DIR / "scripts/training"
EVALUATION_DIR = ROOT_DIR / "data/evaluation/condition_model"
REPORT_DIR = ROOT_DIR / "data/reports/condition_model"
MODEL_PATH = ROOT_DIR / "models/runtime/condition_mvp_model.pkl"

sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(TRAINING_SCRIPT_DIR))

from entrenar_modelo_condiciones import generate_dataset, load_knowledge


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def safe_divide(numerator: int, denominator: int) -> float | str:
    if denominator == 0:
        return ""
    return round(float(numerator / denominator), 4)


def safe_f1(y_true: np.ndarray, y_pred: np.ndarray, average: str) -> float:
    value = f1_score(y_true, y_pred, average=average, zero_division=0)
    if not math.isfinite(float(value)):
        return 0.0
    return round(float(value), 4)


def load_model() -> dict[str, Any]:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"No existe modelo condition_mvp: {MODEL_PATH}")
    return joblib.load(MODEL_PATH)


def evaluate(rows: int, seed: int) -> dict[str, Any]:
    if rows < 1000:
        raise ValueError("--rows debe ser al menos 1000 para esta evaluacion.")

    generated_at = utc_now()
    artifact = load_model()
    labels: list[str] = artifact["labels"]
    cat_cols: list[str] = artifact["cat_cols"]
    num_cols: list[str] = artifact["num_cols"]
    thresholds: dict[str, float] = artifact["thresholds"]
    pipeline = artifact["pipeline"]

    knowledge = load_knowledge()
    df = generate_dataset(knowledge, n_rows=rows, seed=seed)
    target_cols = [f"target_{label}" for label in labels]
    x = df[cat_cols + num_cols]
    y_true = df[target_cols].to_numpy(dtype=int)
    probabilities = pipeline.predict_proba(x)
    threshold_array = np.array([thresholds[label] for label in labels])
    y_pred = (probabilities >= threshold_array).astype(int)

    EVALUATION_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    holdout_path = EVALUATION_DIR / f"holdout_{rows}_cases.csv"
    summary_path = REPORT_DIR / f"06_holdout_{rows}_summary.csv"
    label_path = REPORT_DIR / f"06_holdout_{rows}_condition_metrics.csv"
    case_path = REPORT_DIR / f"06_holdout_{rows}_case_results.csv"
    false_negative_path = REPORT_DIR / f"06_holdout_{rows}_false_negatives.csv"
    false_positive_path = REPORT_DIR / f"06_holdout_{rows}_false_positives.csv"

    df.to_csv(holdout_path, index=False)

    exact_match = np.all(y_true == y_pred, axis=1)
    target_counts = y_true.sum(axis=1)
    predicted_counts = y_pred.sum(axis=1)
    case_rows = []
    false_negative_rows = []
    false_positive_rows = []
    for row_index in range(rows):
        expected = [labels[i] for i, value in enumerate(y_true[row_index]) if value == 1]
        predicted = [labels[i] for i, value in enumerate(y_pred[row_index]) if value == 1]
        missing = sorted(set(expected) - set(predicted))
        unexpected = sorted(set(predicted) - set(expected))
        top_index = int(np.argmax(probabilities[row_index]))
        case_id = f"holdout_{seed}_{row_index + 1:04d}"
        case_rows.append(
            {
                "generated_at": generated_at,
                "case_id": case_id,
                "row_index": row_index,
                "exact_match": bool(exact_match[row_index]),
                "expected_positive_count": int(target_counts[row_index]),
                "predicted_positive_count": int(predicted_counts[row_index]),
                "expected_positive": "|".join(expected),
                "predicted_positive": "|".join(predicted),
                "missing_expected_positive": "|".join(missing),
                "unexpected_positive": "|".join(unexpected),
                "top_condition": labels[top_index],
                "top_probability": round(float(probabilities[row_index, top_index]), 4),
            }
        )
        for condition in missing:
            condition_index = labels.index(condition)
            false_negative_rows.append(
                {
                    "generated_at": generated_at,
                    "case_id": case_id,
                    "condition": condition,
                    "probability": round(float(probabilities[row_index, condition_index]), 4),
                    "threshold": thresholds[condition],
                    "rule_score": df.iloc[row_index].get(f"rule_score_{condition}", ""),
                    "evidence": df.iloc[row_index].get(f"evidence_{condition}", ""),
                }
            )
        for condition in unexpected:
            condition_index = labels.index(condition)
            false_positive_rows.append(
                {
                    "generated_at": generated_at,
                    "case_id": case_id,
                    "condition": condition,
                    "probability": round(float(probabilities[row_index, condition_index]), 4),
                    "threshold": thresholds[condition],
                    "rule_score": df.iloc[row_index].get(f"rule_score_{condition}", ""),
                    "evidence": df.iloc[row_index].get(f"evidence_{condition}", ""),
                }
            )

    per_label_rows = []
    for index, label in enumerate(labels):
        true_col = y_true[:, index]
        pred_col = y_pred[:, index]
        tp = int(((true_col == 1) & (pred_col == 1)).sum())
        fn = int(((true_col == 1) & (pred_col == 0)).sum())
        fp = int(((true_col == 0) & (pred_col == 1)).sum())
        tn = int(((true_col == 0) & (pred_col == 0)).sum())
        per_label_rows.append(
            {
                "generated_at": generated_at,
                "condition": label,
                "threshold": thresholds[label],
                "prevalence": round(float(true_col.mean()), 4),
                "predicted_positive_rate": round(float(pred_col.mean()), 4),
                "tp": tp,
                "fn": fn,
                "fp": fp,
                "tn": tn,
                "precision": safe_divide(tp, tp + fp),
                "recall": safe_divide(tp, tp + fn),
                "specificity": safe_divide(tn, tn + fp),
                "f1": round(float(f1_score(true_col, pred_col, zero_division=0)), 4),
                "mean_probability_positive": round(float(probabilities[true_col == 1, index].mean()), 4) if int(true_col.sum()) else "",
                "mean_probability_negative": round(float(probabilities[true_col == 0, index].mean()), 4) if int((true_col == 0).sum()) else "",
            }
        )

    summary = [
        {
            "generated_at": generated_at,
            "rows": rows,
            "seed": seed,
            "label_count": len(labels),
            "feature_count": len(cat_cols) + len(num_cols),
            "model_trained_at": artifact.get("trained_at", ""),
            "hamming_loss": round(float(hamming_loss(y_true, y_pred)), 4),
            "f1_macro": safe_f1(y_true, y_pred, "macro"),
            "f1_micro": safe_f1(y_true, y_pred, "micro"),
            "f1_samples": safe_f1(y_true, y_pred, "samples"),
            "precision_macro": round(float(precision_score(y_true, y_pred, average="macro", zero_division=0)), 4),
            "recall_macro": round(float(recall_score(y_true, y_pred, average="macro", zero_division=0)), 4),
            "exact_match_rate": round(float(exact_match.mean()), 4),
            "cases_with_false_negative": sum(1 for row in case_rows if row["missing_expected_positive"]),
            "cases_with_false_positive": sum(1 for row in case_rows if row["unexpected_positive"]),
            "false_negative_count": len(false_negative_rows),
            "false_positive_count": len(false_positive_rows),
            "holdout_path": str(holdout_path.relative_to(ROOT_DIR)),
            "case_results_path": str(case_path.relative_to(ROOT_DIR)),
            "condition_metrics_path": str(label_path.relative_to(ROOT_DIR)),
        }
    ]

    pd.DataFrame(summary).to_csv(summary_path, index=False)
    pd.DataFrame(per_label_rows).to_csv(label_path, index=False)
    pd.DataFrame(case_rows).to_csv(case_path, index=False)
    pd.DataFrame(false_negative_rows).to_csv(false_negative_path, index=False)
    pd.DataFrame(false_positive_rows).to_csv(false_positive_path, index=False)

    return {
        "summary": summary[0],
        "summary_path": summary_path,
        "label_path": label_path,
        "case_path": case_path,
        "false_negative_path": false_negative_path,
        "false_positive_path": false_positive_path,
    }


def run(args: argparse.Namespace) -> None:
    result = evaluate(rows=args.rows, seed=args.seed)
    summary = result["summary"]
    print("Evaluacion holdout condition_mvp completada")
    print(f"  rows: {summary['rows']}")
    print(f"  seed: {summary['seed']}")
    print(f"  model_trained_at: {summary['model_trained_at']}")
    print(f"  f1_macro: {summary['f1_macro']}")
    print(f"  hamming_loss: {summary['hamming_loss']}")
    print(f"  exact_match_rate: {summary['exact_match_rate']}")
    print(f"  false_negative_count: {summary['false_negative_count']}")
    print(f"  false_positive_count: {summary['false_positive_count']}")
    print(f"  resumen: {result['summary_path']}")
    print(f"  metricas por condicion: {result['label_path']}")
    print(f"  casos: {result['case_path']}")

    if args.min_f1_macro is not None and float(summary["f1_macro"]) < args.min_f1_macro:
        raise SystemExit(f"f1_macro {summary['f1_macro']} menor a {args.min_f1_macro}")
    if args.max_hamming_loss is not None and float(summary["hamming_loss"]) > args.max_hamming_loss:
        raise SystemExit(f"hamming_loss {summary['hamming_loss']} mayor a {args.max_hamming_loss}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evalua condition_mvp con holdout semisintetico nuevo.")
    parser.add_argument("--rows", type=int, default=1000, help="Cantidad de casos holdout. Minimo 1000.")
    parser.add_argument("--seed", type=int, default=20260617, help="Semilla distinta a la de entrenamiento.")
    parser.add_argument("--min-f1-macro", type=float, default=None, help="Falla si f1_macro queda debajo del umbral.")
    parser.add_argument("--max-hamming-loss", type=float, default=None, help="Falla si hamming_loss queda sobre el umbral.")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
