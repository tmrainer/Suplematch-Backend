#!/usr/bin/env python3
"""Importa casos publicos de NHANES para evaluar condition_mvp.

NHANES publica datos de uso publico por componentes en formato SAS XPT.
Este importador descarga archivos oficiales CDC, los une por SEQN, elimina
SEQN de la salida y genera features anonimas compatibles con condition_mvp.

No entrena el modelo ni crea diagnosticos. Produce casos reales no etiquetados
para revisar distribucion, calibracion y predicciones sobre laboratorios reales.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[2]
TRAINING_SCRIPT_DIR = ROOT_DIR / "scripts/training"
RAW_DIR = ROOT_DIR / "data/raw/nhanes/2017_2018"
REAL_CASES_DIR = ROOT_DIR / "data/evaluation/condition_model/real_cases"
REPORT_DIR = ROOT_DIR / "data/reports/condition_model"

DEFAULT_OUTPUT = REAL_CASES_DIR / "nhanes_2017_2018_condition_cases.csv"
DEFAULT_PREDICTIONS = REPORT_DIR / "08_nhanes_2017_2018_predictions.csv"
DEFAULT_SUMMARY = REPORT_DIR / "08_nhanes_2017_2018_summary.csv"
DEFAULT_CONDITION_SUMMARY = REPORT_DIR / "08_nhanes_2017_2018_condition_summary.csv"
DEFAULT_SOURCE_MANIFEST = REPORT_DIR / "08_nhanes_2017_2018_source_manifest.csv"

CDC_BASE_URL = "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles"
NHANES_FILES = {
    "DEMO_J": "Demographics",
    "BMX_J": "Body Measures",
    "BIOPRO_J": "Standard Biochemistry Profile",
    "CBC_J": "Complete Blood Count",
    "TCHOL_J": "Total Cholesterol",
    "HDL_J": "HDL Cholesterol",
    "TRIGLY_J": "Triglycerides and LDL",
    "GLU_J": "Fasting Glucose",
    "VID_J": "Vitamin D",
    "VIC_J": "Vitamin C",
    "FOLATE_J": "RBC Folate",
    "FERTIN_J": "Ferritin",
}

sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(TRAINING_SCRIPT_DIR))

from app.ml.runtime.condition_mvp_inference import _prepare_features, predict_condition_probabilities
from entrenar_modelo_condiciones import CAT_COLS, NUM_COLS, load_knowledge


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT_DIR)) if path.is_relative_to(ROOT_DIR) else str(path)


def file_url(file_code: str) -> str:
    return f"{CDC_BASE_URL}/{file_code}.XPT"


def download_file(file_code: str, force: bool = False) -> tuple[Path | None, dict[str, Any]]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{file_code}.XPT"
    url = file_url(file_code)
    row: dict[str, Any] = {
        "file_code": file_code,
        "description": NHANES_FILES[file_code],
        "url": url,
        "local_path": rel(path),
        "status": "pending",
        "bytes": "",
    }
    if path.exists() and not force:
        row["status"] = "cached"
        row["bytes"] = path.stat().st_size
        return path, row

    try:
        request = Request(url, headers={"User-Agent": "SupleMatch-MVP/1.0"})
        with urlopen(request, timeout=90) as response:
            data = response.read()
    except (HTTPError, URLError, TimeoutError) as exc:
        row["status"] = "download_error"
        row["error"] = str(exc)
        return None, row

    if len(data) < 10_000 or data[:20].lstrip().lower().startswith(b"<!doctype"):
        row["status"] = "invalid_response"
        row["bytes"] = len(data)
        return None, row

    path.write_bytes(data)
    row["status"] = "downloaded"
    row["bytes"] = len(data)
    return path, row


def read_xpt(path: Path, columns: list[str] | None = None) -> pd.DataFrame:
    frame = pd.read_sas(path, format="xport", encoding="utf-8")
    if columns:
        present = [column for column in columns if column in frame.columns]
        frame = frame[present]
    return frame


def merge_components(files: dict[str, Path]) -> pd.DataFrame:
    column_map = {
        "DEMO_J": ["SEQN", "RIAGENDR", "RIDAGEYR"],
        "BMX_J": ["SEQN", "BMXWT", "BMXHT", "BMXBMI"],
        "BIOPRO_J": ["SEQN", "LBXSCR", "LBXSCA", "LBXSATSI", "LBXSASSI"],
        "CBC_J": ["SEQN", "LBXHGB"],
        "TCHOL_J": ["SEQN", "LBXTC"],
        "HDL_J": ["SEQN", "LBDHDD"],
        "TRIGLY_J": ["SEQN", "LBXTR", "LBDLDL"],
        "GLU_J": ["SEQN", "LBXGLU"],
        "VID_J": ["SEQN", "LBXVIDMS"],
        "VIC_J": ["SEQN", "LBXVIC", "LBDVICSI"],
        "FOLATE_J": ["SEQN", "LBDRFO"],
        "FERTIN_J": ["SEQN", "LBXFER"],
    }
    merged: pd.DataFrame | None = None
    for file_code, columns in column_map.items():
        if file_code not in files:
            continue
        frame = read_xpt(files[file_code], columns=columns)
        if "SEQN" not in frame.columns:
            continue
        frame = frame.drop_duplicates(subset=["SEQN"])
        merged = frame if merged is None else merged.merge(frame, on="SEQN", how="left")
    if merged is None or merged.empty:
        raise RuntimeError("No se pudo unir ningun componente NHANES con SEQN.")
    return merged


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number):
        return None
    return number


def status_low_high(
    value: Any,
    *,
    low: float | None = None,
    critical_low: float | None = None,
    high: float | None = None,
    critical_high: float | None = None,
) -> str:
    number = safe_float(value)
    if number is None:
        return "missing"
    if critical_low is not None and number < critical_low:
        return "critical_low"
    if low is not None and number < low:
        return "low"
    if critical_high is not None and number >= critical_high:
        return "critical_high"
    if high is not None and number >= high:
        return "high"
    return "normal"


def hemoglobin_status(value: Any, sexo: str) -> str:
    number = safe_float(value)
    if number is None:
        return "missing"
    if number < 10:
        return "critical_low"
    low_cutoff = 12.0 if sexo == "F" else 13.0
    return "low" if number < low_cutoff else "normal"


def hdl_status(value: Any, sexo: str) -> str:
    number = safe_float(value)
    if number is None:
        return "missing"
    if number < 30:
        return "critical_low"
    low_cutoff = 50.0 if sexo == "F" else 40.0
    return "low" if number < low_cutoff else "normal"


def egfr_2021_creatinine(creatinine_mg_dl: Any, age: Any, sexo: str) -> float | None:
    scr = safe_float(creatinine_mg_dl)
    age_years = safe_float(age)
    if scr is None or age_years is None or scr <= 0 or age_years <= 0:
        return None
    female = sexo == "F"
    kappa = 0.7 if female else 0.9
    alpha = -0.241 if female else -0.302
    ratio = scr / kappa
    egfr = 142 * (min(ratio, 1) ** alpha) * (max(ratio, 1) ** -1.200) * (0.9938**age_years)
    if female:
        egfr *= 1.012
    return round(egfr, 1)


def egfr_status(value: float | None) -> str:
    if value is None:
        return "missing"
    if value < 30:
        return "critical_low"
    if value < 60:
        return "low"
    return "normal"


def source_case_id(seqn: Any) -> str:
    number = int(float(seqn))
    return f"NHANES-2017-2018-{number}"


def hash_case_id(source_id: str, salt: str) -> str:
    digest = hashlib.sha256(f"{salt}:{source_id}".encode("utf-8")).hexdigest()
    return f"nhanes_{digest[:20]}"


def nhanes_row_to_features(row: pd.Series, salt: str, generated_at: str) -> dict[str, Any] | None:
    seqn = safe_float(row.get("SEQN"))
    age = safe_float(row.get("RIDAGEYR"))
    weight = safe_float(row.get("BMXWT"))
    height = safe_float(row.get("BMXHT"))
    bmi = safe_float(row.get("BMXBMI"))
    if seqn is None or age is None or age < 18 or weight is None or height is None or bmi is None:
        return None

    sexo = "M" if safe_float(row.get("RIAGENDR")) == 1 else "F"
    egfr = egfr_2021_creatinine(row.get("LBXSCR"), age, sexo)
    source_id = source_case_id(seqn)
    partial_features = {
        "sexo": sexo,
        "tipo_dieta": "unknown",
        "exposicion_solar": "unknown",
        "nivel_actividad": "unknown",
        "lab_panel_source": "nhanes_2017_2018_public_xpt",
        "edad": int(age),
        "peso_kg": round(weight, 2),
        "altura_cm": round(height, 2),
        "bmi": round(bmi, 2),
        "fatiga_general": 1,
        "dolor_muscular": 1,
        "dolor_articular": 1,
        "niebla_mental": 1,
        "problemas_sueno": 1,
        "caida_cabello": 1,
        "piel_seca": 1,
        "unas_quebradizas": 1,
        "enfermedad_frecuente": 1,
        "calambres": 1,
        "irritabilidad": 1,
        "dieta_deficiente": 0,
        "estres_alto": 0,
        "meta_energia": 0,
        "meta_inmunidad": 0,
        "meta_belleza": 0,
        "meta_rendimiento": 0,
        "meta_salud_osea": 0,
        "meta_cognitivo": 0,
        "lab_vitamin_d_status": status_low_high(row.get("LBXVIDMS"), low=50, critical_low=30),
        "lab_b12_status": "missing",
        "lab_ferritin_status": status_low_high(row.get("LBXFER"), low=15, critical_low=10),
        "lab_hemoglobin_status": hemoglobin_status(row.get("LBXHGB"), sexo),
        "lab_magnesium_status": "missing",
        "lab_zinc_status": "missing",
        "lab_calcium_status": status_low_high(row.get("LBXSCA"), low=8.6, critical_low=7.5, high=10.5, critical_high=12),
        "lab_folate_status": status_low_high(row.get("LBDRFO"), low=317, critical_low=226),
        "lab_glucose_status": status_low_high(row.get("LBXGLU"), high=126, critical_high=200),
        "lab_total_cholesterol_status": status_low_high(row.get("LBXTC"), high=240),
        "lab_ldl_status": status_low_high(row.get("LBDLDL"), high=160),
        "lab_hdl_status": hdl_status(row.get("LBDHDD"), sexo),
        "lab_triglycerides_status": status_low_high(row.get("LBXTR"), high=200, critical_high=500),
        "lab_creatinine_status": status_low_high(
            row.get("LBXSCR"),
            high=1.1 if sexo == "F" else 1.3,
            critical_high=2.0,
        ),
        "lab_egfr_status": egfr_status(egfr),
        "lab_alt_status": status_low_high(row.get("LBXSATSI"), high=40, critical_high=120),
        "lab_ast_status": status_low_high(row.get("LBXSASSI"), high=40, critical_high=120),
        "lab_tsh_status": "missing",
    }
    prepared = _prepare_features(partial_features, CAT_COLS, NUM_COLS)
    normalized = {
        "generated_at": generated_at,
        "case_id": hash_case_id(source_id, salt),
        "collected_at": "2017-2018",
        "data_source": "CDC NHANES public-use 2017-2018",
        "reviewer_code": "unreviewed_public_dataset",
        "expected_positive": "",
        "expected_negative": "",
    }
    for column in CAT_COLS + NUM_COLS:
        normalized[column] = prepared[column]
    normalized["benchmark_lab_vitamin_c_status"] = status_low_high(row.get("LBDVICSI"), low=23, critical_low=11.4)
    normalized["benchmark_lab_vitamin_c_observed"] = int(normalized["benchmark_lab_vitamin_c_status"] != "missing")
    return normalized


def prediction_rows(cases: list[dict[str, Any]], generated_at: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        features = {column: case[column] for column in CAT_COLS + NUM_COLS if column in case}
        for prediction in predict_condition_probabilities(features):
            rows.append(
                {
                    "generated_at": generated_at,
                    "case_id": case["case_id"],
                    "condition": prediction["condition"],
                    "expected_state": "unreviewed",
                    "positive": prediction["positive"],
                    "probability": prediction["probability"],
                    "threshold": prediction["threshold"],
                    "evidence_level": prediction["evidence_level"],
                    "drivers": "|".join(prediction.get("drivers", [])),
                    "missing_data": "|".join(prediction.get("missing_data", [])),
                    "safety_flag": prediction["safety_flag"],
                }
            )
    return rows


def summarize_conditions(predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    frame = pd.DataFrame(predictions)
    if frame.empty:
        return []
    grouped = []
    for condition, group in frame.groupby("condition"):
        grouped.append(
            {
                "condition": condition,
                "cases": len(group),
                "positive_cases": int(group["positive"].astype(bool).sum()),
                "positive_rate": round(float(group["positive"].astype(bool).mean()), 4),
                "mean_probability": round(float(group["probability"].astype(float).mean()), 4),
                "p95_probability": round(float(group["probability"].astype(float).quantile(0.95)), 4),
            }
        )
    return sorted(grouped, key=lambda item: item["condition"])


def run(args: argparse.Namespace) -> None:
    generated_at = utc_now()
    salt = args.salt or os.getenv("NHANES_CASE_HASH_SALT") or "suplematch-nhanes-public-demo-salt"
    output_path = Path(args.output)
    predictions_path = Path(args.predictions)
    summary_path = Path(args.summary)
    condition_summary_path = Path(args.condition_summary)
    source_manifest_path = Path(args.source_manifest)

    files: dict[str, Path] = {}
    manifest = []
    for file_code in NHANES_FILES:
        path, row = download_file(file_code, force=args.force_download)
        manifest.append(row)
        if path is not None:
            files[file_code] = path

    source_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(manifest).to_csv(source_manifest_path, index=False)

    required = {"DEMO_J", "BMX_J"}
    missing_required = sorted(required - set(files))
    if missing_required:
        raise SystemExit(f"Faltan archivos NHANES requeridos: {', '.join(missing_required)}")

    merged = merge_components(files)
    cases: list[dict[str, Any]] = []
    for _, row in merged.iterrows():
        normalized = nhanes_row_to_features(row, salt=salt, generated_at=generated_at)
        if normalized:
            cases.append(normalized)
        if args.limit and len(cases) >= args.limit:
            break

    if not cases:
        raise SystemExit("No se generaron casos NHANES validos.")

    knowledge = load_knowledge()
    labels = knowledge["conditions"]["labels"]
    predictions = prediction_rows(cases, generated_at=generated_at)
    condition_summary = summarize_conditions(predictions)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    predictions_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    condition_summary_path.parent.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(cases).to_csv(output_path, index=False)
    pd.DataFrame(predictions).to_csv(predictions_path, index=False)
    pd.DataFrame(condition_summary).to_csv(condition_summary_path, index=False)
    pd.DataFrame(
        [
            {
                "generated_at": generated_at,
                "source": "CDC NHANES public-use 2017-2018",
                "source_page": "https://wwwn.cdc.gov/nchs/nhanes/",
                "cdc_data_base_url": CDC_BASE_URL,
                "raw_component_files": len(files),
                "merged_rows": len(merged),
                "accepted_cases": len(cases),
                "prediction_rows": len(predictions),
                "condition_labels": len(labels),
                "minimum_age": 18,
                "seqn_in_output": False,
                "salt_source": "arg_or_env" if args.salt or os.getenv("NHANES_CASE_HASH_SALT") else "local_default_demo_only",
                "output_path": rel(output_path),
                "predictions_path": rel(predictions_path),
                "condition_summary_path": rel(condition_summary_path),
                "source_manifest_path": rel(source_manifest_path),
                "clinical_validation": "not_clinically_validated",
            }
        ]
    ).to_csv(summary_path, index=False)

    print("Importacion NHANES condition_mvp completada")
    print(f"  archivos usados: {len(files)}")
    print(f"  filas unidas: {len(merged)}")
    print(f"  casos aceptados: {len(cases)}")
    print(f"  predicciones: {len(predictions)}")
    print(f"  output: {output_path}")
    print(f"  resumen: {summary_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Importa NHANES 2017-2018 como casos reales anonimos para condition_mvp.")
    parser.add_argument("--limit", type=int, default=1000, help="Cantidad maxima de casos adultos a exportar. 0 = todos.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="CSV de casos anonimos.")
    parser.add_argument("--predictions", default=str(DEFAULT_PREDICTIONS), help="CSV de predicciones.")
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY), help="CSV resumen.")
    parser.add_argument("--condition-summary", default=str(DEFAULT_CONDITION_SUMMARY), help="CSV resumen por condicion.")
    parser.add_argument("--source-manifest", default=str(DEFAULT_SOURCE_MANIFEST), help="CSV manifest de fuentes descargadas.")
    parser.add_argument("--salt", default=None, help="Salt para hash irreversible. Preferir env NHANES_CASE_HASH_SALT.")
    parser.add_argument("--force-download", action="store_true", help="Descarga de nuevo aunque exista cache local.")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
