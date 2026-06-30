#!/usr/bin/env python3
"""Evalua el modelo condition_mvp contra casos golden fijos.

Los casos golden no validan clinicamente el modelo. Sirven como regresion
funcional: condiciones obvias deben activarse y negativos criticos no deben
activarse.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CASES = ROOT_DIR / "data/evaluation/condition_model/golden_cases.csv"
REPORT_DIR = ROOT_DIR / "data/reports/condition_model"
sys.path.insert(0, str(ROOT_DIR))

from app.ml.runtime.condition_mvp_inference import predict_condition_probabilities


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def split_pipe(value: str) -> set[str]:
    text = str(value or "").strip()
    if not text:
        return set()
    return {item.strip() for item in text.split("|") if item.strip()}


def parse_scalar(value: str) -> Any:
    text = value.strip()
    if text in {"true", "True"}:
        return True
    if text in {"false", "False"}:
        return False
    try:
        number = float(text)
    except ValueError:
        return text
    if number.is_integer():
        return int(number)
    return number


def parse_feature_overrides(value: str) -> dict[str, Any]:
    features: dict[str, Any] = {}
    text = str(value or "").strip()
    if not text:
        return features
    for item in text.split(";"):
        if not item.strip():
            continue
        if "=" not in item:
            raise ValueError(f"Feature override invalido: {item}")
        key, raw_value = item.split("=", 1)
        features[key.strip()] = parse_scalar(raw_value)
    return features


def load_cases(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"No hay casos golden en {path}")
    case_ids = [row["case_id"] for row in rows]
    duplicates = sorted({case_id for case_id in case_ids if case_ids.count(case_id) > 1})
    if duplicates:
        raise ValueError(f"case_id duplicado: {duplicates}")
    return rows


def evaluate_case(row: dict[str, str], generated_at: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    expected_positive = split_pipe(row["expected_positive"])
    expected_negative = split_pipe(row["expected_negative"])
    features = parse_feature_overrides(row["feature_overrides"])
    predictions = predict_condition_probabilities(features)
    by_condition = {item["condition"]: item for item in predictions}
    predicted_positive = {item["condition"] for item in predictions if item["positive"]}

    missing_expected_positive = sorted(expected_positive - predicted_positive)
    unexpected_positive = sorted(expected_negative & predicted_positive)
    extra_positive = sorted(predicted_positive - expected_positive)
    passed = not missing_expected_positive and not unexpected_positive

    top = predictions[0] if predictions else {}
    case_result = {
        "generated_at": generated_at,
        "case_id": row["case_id"],
        "category": row["category"],
        "description": row["description"],
        "passed": passed,
        "expected_positive": "|".join(sorted(expected_positive)),
        "expected_negative": "|".join(sorted(expected_negative)),
        "predicted_positive": "|".join(sorted(predicted_positive)),
        "missing_expected_positive": "|".join(missing_expected_positive),
        "unexpected_positive": "|".join(unexpected_positive),
        "extra_positive": "|".join(extra_positive),
        "top_condition": top.get("condition", ""),
        "top_probability": top.get("probability", ""),
    }

    condition_rows = []
    for condition, prediction in by_condition.items():
        expected_state = (
            "positive"
            if condition in expected_positive
            else "negative"
            if condition in expected_negative
            else "unspecified"
        )
        if expected_state == "positive":
            outcome = "tp" if prediction["positive"] else "fn"
        elif expected_state == "negative":
            outcome = "fp" if prediction["positive"] else "tn"
        else:
            outcome = "extra_positive" if prediction["positive"] else "ignored_negative"
        condition_rows.append(
            {
                "generated_at": generated_at,
                "case_id": row["case_id"],
                "category": row["category"],
                "condition": condition,
                "expected_state": expected_state,
                "outcome": outcome,
                "positive": prediction["positive"],
                "probability": prediction["probability"],
                "threshold": prediction["threshold"],
                "evidence_level": prediction["evidence_level"],
                "drivers": "|".join(prediction.get("drivers", [])),
                "missing_data": "|".join(prediction.get("missing_data", [])),
                "safety_flag": prediction["safety_flag"],
            }
        )
    return case_result, condition_rows


def summarize(case_results: list[dict[str, Any]], condition_results: list[dict[str, Any]], generated_at: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    total_cases = len(case_results)
    passed_cases = sum(1 for item in case_results if item["passed"])
    failed_cases = total_cases - passed_cases

    summary = [
        {
            "generated_at": generated_at,
            "total_cases": total_cases,
            "passed_cases": passed_cases,
            "failed_cases": failed_cases,
            "case_pass_rate": round(passed_cases / total_cases, 4) if total_cases else 0.0,
        }
    ]

    by_condition: dict[str, dict[str, int]] = {}
    for row in condition_results:
        condition = row["condition"]
        bucket = by_condition.setdefault(
            condition,
            {"expected_positive": 0, "expected_negative": 0, "tp": 0, "fn": 0, "tn": 0, "fp": 0},
        )
        outcome = row["outcome"]
        if row["expected_state"] == "positive":
            bucket["expected_positive"] += 1
        elif row["expected_state"] == "negative":
            bucket["expected_negative"] += 1
        if outcome in bucket:
            bucket[outcome] += 1

    condition_summary = []
    for condition, values in sorted(by_condition.items()):
        expected_positive = values["expected_positive"]
        expected_negative = values["expected_negative"]
        recall = values["tp"] / expected_positive if expected_positive else None
        specificity = values["tn"] / expected_negative if expected_negative else None
        condition_summary.append(
            {
                "generated_at": generated_at,
                "condition": condition,
                **values,
                "golden_recall": round(recall, 4) if recall is not None else "",
                "golden_specificity": round(specificity, 4) if specificity is not None else "",
            }
        )
    return summary, condition_summary


def run(args: argparse.Namespace) -> None:
    cases_path = Path(args.cases)
    generated_at = utc_now()
    cases = load_cases(cases_path)
    case_results: list[dict[str, Any]] = []
    condition_results: list[dict[str, Any]] = []
    for row in cases:
        case_result, condition_rows = evaluate_case(row, generated_at)
        case_results.append(case_result)
        condition_results.extend(condition_rows)

    summary, condition_summary = summarize(case_results, condition_results, generated_at)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    case_path = REPORT_DIR / "05_golden_case_results.csv"
    detail_path = REPORT_DIR / "05_golden_condition_details.csv"
    summary_path = REPORT_DIR / "05_golden_summary.csv"
    condition_summary_path = REPORT_DIR / "05_golden_condition_summary.csv"
    pd.DataFrame(case_results).to_csv(case_path, index=False)
    pd.DataFrame(condition_results).to_csv(detail_path, index=False)
    pd.DataFrame(summary).to_csv(summary_path, index=False)
    pd.DataFrame(condition_summary).to_csv(condition_summary_path, index=False)

    print("Evaluacion golden condition_mvp completada")
    print(f"  casos: {len(case_results)}")
    print(f"  pass_rate: {summary[0]['case_pass_rate']}")
    print(f"  resumen: {summary_path}")
    print(f"  casos detalle: {case_path}")
    print(f"  condiciones detalle: {detail_path}")
    print(f"  condiciones resumen: {condition_summary_path}")

    if args.fail_on_case_failure and summary[0]["failed_cases"]:
        raise SystemExit(f"Fallaron {summary[0]['failed_cases']} casos golden.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evalua condition_mvp con casos golden fijos.")
    parser.add_argument("--cases", default=str(DEFAULT_CASES), help="CSV de casos golden.")
    parser.add_argument("--fail-on-case-failure", action="store_true", help="Sale con error si falla algun caso.")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
