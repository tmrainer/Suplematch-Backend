#!/usr/bin/env python3
"""Prepara casos reales anonimizados para condition_mvp.

Entrada esperada: CSV sin PII directa. El unico identificador permitido es
`source_case_id`, que se transforma a un hash irreversible.

Este script no entrena el modelo. Produce un dataset anonimo, reportes de
rechazo y predicciones del modelo actual para auditoria.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[2]
TRAINING_SCRIPT_DIR = ROOT_DIR / "scripts/training"
REAL_CASES_DIR = ROOT_DIR / "data/evaluation/condition_model/real_cases"
REPORT_DIR = ROOT_DIR / "data/reports/condition_model"
DEFAULT_INPUT = REAL_CASES_DIR / "real_cases_template.csv"
DEFAULT_OUTPUT = REAL_CASES_DIR / "real_cases_anonymized.csv"
DEFAULT_REJECTED = REPORT_DIR / "07_real_cases_rejected.csv"
DEFAULT_PREDICTIONS = REPORT_DIR / "07_real_cases_predictions.csv"
DEFAULT_SUMMARY = REPORT_DIR / "07_real_cases_summary.csv"

sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(TRAINING_SCRIPT_DIR))

from app.ml.runtime.condition_mvp_inference import _prepare_features, predict_condition_probabilities
from entrenar_modelo_condiciones import CAT_COLS, NUM_COLS, SOFT_SIGNAL_COLS, load_knowledge


TRUE_VALUES = {"1", "true", "t", "yes", "y", "si", "sí"}
FALSE_VALUES = {"0", "false", "f", "no", "n"}
SCALAR_TRUE_VALUES = {"1", "true", "yes", "si", "sí"}
SCALAR_FALSE_VALUES = {"0", "false", "no"}
PII_COLUMN_PATTERNS = [
    "email",
    "correo",
    "mail",
    "name",
    "nombre",
    "apellido",
    "phone",
    "telefono",
    "teléfono",
    "dni",
    "document",
    "documento",
    "passport",
    "pasaporte",
    "address",
    "direccion",
    "dirección",
    "date_of_birth",
    "birth_date",
    "fecha_nacimiento",
    "dob",
]
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)")
PHONE_SCAN_EXCLUDED_COLUMNS = {"source_case_id", "collected_at"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def split_pipe(value: str) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    return [item.strip() for item in text.split("|") if item.strip()]


def parse_scalar(value: Any) -> Any:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    lowered = text.lower()
    if lowered in SCALAR_TRUE_VALUES:
        return 1
    if lowered in SCALAR_FALSE_VALUES:
        return 0
    try:
        number = float(text)
    except ValueError:
        return text
    if number.is_integer():
        return int(number)
    return number


def parse_bool(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if text in TRUE_VALUES:
        return True
    if text in FALSE_VALUES:
        return False
    return False


def hash_case_id(source_case_id: str, salt: str) -> str:
    digest = hashlib.sha256(f"{salt}:{source_case_id}".encode("utf-8")).hexdigest()
    return f"real_{digest[:20]}"


def has_pii_columns(columns: list[str]) -> list[str]:
    found = []
    for col in columns:
        normalized = col.strip().lower()
        if normalized == "source_case_id":
            continue
        if any(pattern in normalized for pattern in PII_COLUMN_PATTERNS):
            found.append(col)
    return found


def has_pii_values(row: dict[str, Any]) -> list[str]:
    findings = []
    numeric_columns = set(NUM_COLS) | set(SOFT_SIGNAL_COLS)
    for key, value in row.items():
        if key == "source_case_id":
            continue
        text = str(value or "")
        if EMAIL_PATTERN.search(text):
            findings.append(f"{key}:email")
        elif key not in PHONE_SCAN_EXCLUDED_COLUMNS and key not in numeric_columns and PHONE_PATTERN.search(text):
            findings.append(f"{key}:phone_like")
    return findings


def allowed_columns(labels: set[str]) -> set[str]:
    metadata = {
        "source_case_id",
        "consent_for_training",
        "collected_at",
        "data_source",
        "reviewer_code",
        "expected_positive",
        "expected_negative",
    }
    return metadata | set(CAT_COLS) | set(NUM_COLS) | set(SOFT_SIGNAL_COLS) | {f"target_{label}" for label in labels}


def validate_expected_labels(row: dict[str, Any], labels: set[str]) -> list[str]:
    errors = []
    positives = set(split_pipe(str(row.get("expected_positive", ""))))
    negatives = set(split_pipe(str(row.get("expected_negative", ""))))
    unknown = sorted((positives | negatives) - labels)
    if unknown:
        errors.append(f"unknown_expected_labels:{'|'.join(unknown)}")
    overlap = sorted(positives & negatives)
    if overlap:
        errors.append(f"label_expected_positive_and_negative:{'|'.join(overlap)}")
    return errors


def normalize_row(raw: dict[str, Any], salt: str, labels: set[str]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    source_case_id = str(raw.get("source_case_id", "")).strip()
    if not source_case_id:
        return None, {"source_case_id": "", "reason": "missing_source_case_id"}
    if not parse_bool(raw.get("consent_for_training")):
        return None, {"source_case_id": source_case_id, "reason": "missing_or_false_consent"}

    pii_findings = has_pii_values(raw)
    if pii_findings:
        return None, {"source_case_id": source_case_id, "reason": "pii_like_value", "details": "|".join(pii_findings)}

    expected_errors = validate_expected_labels(raw, labels)
    if expected_errors:
        return None, {"source_case_id": source_case_id, "reason": "invalid_expected_labels", "details": "|".join(expected_errors)}

    partial_features = {
        key: parse_scalar(value)
        for key, value in raw.items()
        if key in set(CAT_COLS + NUM_COLS + SOFT_SIGNAL_COLS) and str(value or "").strip() != ""
    }
    prepared = _prepare_features(partial_features, CAT_COLS, NUM_COLS)
    case_id = hash_case_id(source_case_id, salt)
    normalized = {
        "case_id": case_id,
        "collected_at": str(raw.get("collected_at", "")).strip(),
        "data_source": str(raw.get("data_source", "")).strip(),
        "reviewer_code": str(raw.get("reviewer_code", "")).strip(),
        "expected_positive": "|".join(split_pipe(str(raw.get("expected_positive", "")))),
        "expected_negative": "|".join(split_pipe(str(raw.get("expected_negative", "")))),
    }
    for col in CAT_COLS + NUM_COLS:
        normalized[col] = prepared[col]
    return normalized, None


def evaluate_predictions(rows: list[dict[str, Any]], labels: set[str], generated_at: str) -> list[dict[str, Any]]:
    prediction_rows = []
    for row in rows:
        features = {col: row[col] for col in CAT_COLS + NUM_COLS if col in row}
        predictions = predict_condition_probabilities(features)
        expected_positive = set(split_pipe(str(row.get("expected_positive", ""))))
        expected_negative = set(split_pipe(str(row.get("expected_negative", ""))))
        for prediction in predictions:
            condition = prediction["condition"]
            expected_state = (
                "positive"
                if condition in expected_positive
                else "negative"
                if condition in expected_negative
                else "unreviewed"
            )
            prediction_rows.append(
                {
                    "generated_at": generated_at,
                    "case_id": row["case_id"],
                    "condition": condition,
                    "expected_state": expected_state,
                    "positive": prediction["positive"],
                    "probability": prediction["probability"],
                    "threshold": prediction["threshold"],
                    "evidence_level": prediction["evidence_level"],
                    "drivers": "|".join(prediction.get("drivers", [])),
                    "missing_data": "|".join(prediction.get("missing_data", [])),
                    "safety_flag": prediction["safety_flag"],
                }
            )
    return prediction_rows


def run(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    output_path = Path(args.output)
    rejected_path = Path(args.rejected)
    predictions_path = Path(args.predictions)
    summary_path = Path(args.summary)
    generated_at = utc_now()
    salt = args.salt or os.getenv("REAL_CASES_HASH_SALT") or "suplematch-university-mvp-local-salt"

    knowledge = load_knowledge()
    labels = set(knowledge["conditions"]["labels"])
    rows = list(csv.DictReader(input_path.open(encoding="utf-8", newline="")))
    if not rows:
        raise SystemExit(f"No hay filas para preparar en {input_path}")

    pii_columns = has_pii_columns(list(rows[0].keys()))
    if pii_columns:
        raise SystemExit(f"Columnas PII no permitidas: {', '.join(pii_columns)}")

    unknown_columns = sorted(set(rows[0].keys()) - allowed_columns(labels))
    if unknown_columns:
        raise SystemExit(f"Columnas no reconocidas: {', '.join(unknown_columns)}")

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for raw in rows:
        normalized, rejection = normalize_row(raw, salt=salt, labels=labels)
        if rejection:
            rejected.append({"generated_at": generated_at, **rejection})
        elif normalized:
            accepted.append({"generated_at": generated_at, **normalized})

    output_path.parent.mkdir(parents=True, exist_ok=True)
    rejected_path.parent.mkdir(parents=True, exist_ok=True)
    predictions_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(accepted).to_csv(output_path, index=False)
    pd.DataFrame(rejected).to_csv(rejected_path, index=False)
    prediction_rows = evaluate_predictions(accepted, labels=labels, generated_at=generated_at)
    pd.DataFrame(prediction_rows).to_csv(predictions_path, index=False)
    summary = [
        {
            "generated_at": generated_at,
            "input_path": str(input_path.relative_to(ROOT_DIR)) if input_path.is_relative_to(ROOT_DIR) else str(input_path),
            "accepted_cases": len(accepted),
            "rejected_cases": len(rejected),
            "prediction_rows": len(prediction_rows),
            "salt_source": "arg_or_env" if args.salt or os.getenv("REAL_CASES_HASH_SALT") else "local_default_demo_only",
            "output_path": str(output_path.relative_to(ROOT_DIR)) if output_path.is_relative_to(ROOT_DIR) else str(output_path),
            "predictions_path": str(predictions_path.relative_to(ROOT_DIR)) if predictions_path.is_relative_to(ROOT_DIR) else str(predictions_path),
            "rejected_path": str(rejected_path.relative_to(ROOT_DIR)) if rejected_path.is_relative_to(ROOT_DIR) else str(rejected_path),
        }
    ]
    pd.DataFrame(summary).to_csv(summary_path, index=False)

    print("Preparacion de casos reales anonimizados completada")
    print(f"  aceptados: {len(accepted)}")
    print(f"  rechazados: {len(rejected)}")
    print(f"  output: {output_path}")
    print(f"  predicciones: {predictions_path}")
    print(f"  rechazados_csv: {rejected_path}")
    print(f"  resumen: {summary_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Anonimiza y valida casos reales para condition_mvp.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="CSV crudo sin PII directa.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="CSV anonimo de salida.")
    parser.add_argument("--rejected", default=str(DEFAULT_REJECTED), help="CSV de filas rechazadas.")
    parser.add_argument("--predictions", default=str(DEFAULT_PREDICTIONS), help="CSV de predicciones por condicion.")
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY), help="CSV resumen.")
    parser.add_argument("--salt", default=None, help="Salt para hash irreversible de source_case_id. Preferir env REAL_CASES_HASH_SALT.")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
