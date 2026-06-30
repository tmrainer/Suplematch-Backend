#!/usr/bin/env python3
"""Importa varios ciclos NHANES como casos reales anonimos para condition_mvp.

Extiende el importador 2017-2018 con ciclos que cubren B12, TSH y nutrientes
dietarios. La salida conserva el contrato de features del modelo y agrega
columnas `benchmark_*` solo para evaluacion semi-curada.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[2]
TRAINING_SCRIPT_DIR = ROOT_DIR / "scripts/training"
RAW_ROOT = ROOT_DIR / "data/raw/nhanes"
REAL_CASES_DIR = ROOT_DIR / "data/evaluation/condition_model/real_cases"
REPORT_DIR = ROOT_DIR / "data/reports/condition_model"

DEFAULT_OUTPUT = REAL_CASES_DIR / "nhanes_multi_cycle_condition_cases.csv"
DEFAULT_PREDICTIONS = REPORT_DIR / "08_nhanes_multi_cycle_predictions.csv"
DEFAULT_SUMMARY = REPORT_DIR / "08_nhanes_multi_cycle_summary.csv"
DEFAULT_CONDITION_SUMMARY = REPORT_DIR / "08_nhanes_multi_cycle_condition_summary.csv"
DEFAULT_SOURCE_MANIFEST = REPORT_DIR / "08_nhanes_multi_cycle_source_manifest.csv"

sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(TRAINING_SCRIPT_DIR))

from app.ml.runtime.condition_mvp_inference import _prepare_features, predict_condition_probabilities
from entrenar_modelo_condiciones import CAT_COLS, NUM_COLS, load_knowledge
from import_nhanes_condition_mvp_cases import (
    egfr_2021_creatinine,
    egfr_status,
    hdl_status,
    hemoglobin_status,
    rel,
    safe_float,
    status_low_high,
    summarize_conditions,
    utc_now,
)


@dataclass(frozen=True)
class CycleConfig:
    cycle: str
    year: str
    suffix: str
    files: dict[str, str]

    @property
    def base_url(self) -> str:
        return f"https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/{self.year}/DataFiles"

    @property
    def raw_dir(self) -> Path:
        return RAW_ROOT / self.cycle

    def file_code(self, stem: str) -> str:
        return f"{stem}_{self.suffix}"


COMMON_FILES = {
    "DEMO": "Demographics",
    "BMX": "Body Measures",
    "BIOPRO": "Standard Biochemistry Profile",
    "CBC": "Complete Blood Count",
    "TCHOL": "Total Cholesterol",
    "HDL": "HDL Cholesterol",
    "TRIGLY": "Triglycerides and LDL",
    "GLU": "Fasting Glucose",
    "VID": "Vitamin D",
    "FOLATE": "RBC Folate",
    "DR1TOT": "Dietary Interview Total Nutrient Intakes Day 1",
}

CYCLES: dict[str, CycleConfig] = {
    "2011_2012": CycleConfig(
        cycle="2011_2012",
        year="2011",
        suffix="G",
        files={
            **COMMON_FILES,
            "VITB12": "Serum Vitamin B12",
            "THYROD": "Thyroid Profile",
        },
    ),
    "2013_2014": CycleConfig(
        cycle="2013_2014",
        year="2013",
        suffix="H",
        files={
            **COMMON_FILES,
            "VITB12": "Serum Vitamin B12",
        },
    ),
    "2015_2016": CycleConfig(
        cycle="2015_2016",
        year="2015",
        suffix="I",
        files={
            **COMMON_FILES,
            "FERTIN": "Ferritin",
        },
    ),
    "2017_2018": CycleConfig(
        cycle="2017_2018",
        year="2017",
        suffix="J",
        files={
            **COMMON_FILES,
            "VIC": "Vitamin C",
            "FERTIN": "Ferritin",
        },
    ),
}

COLUMN_MAP = {
    "DEMO": ["SEQN", "RIAGENDR", "RIDAGEYR"],
    "BMX": ["SEQN", "BMXWT", "BMXHT", "BMXBMI"],
    "BIOPRO": ["SEQN", "LBXSCR", "LBXSCA", "LBXSATSI", "LBXSASSI"],
    "CBC": ["SEQN", "LBXHGB"],
    "TCHOL": ["SEQN", "LBXTC"],
    "HDL": ["SEQN", "LBDHDD"],
    "TRIGLY": ["SEQN", "LBXTR", "LBDLDL"],
    "GLU": ["SEQN", "LBXGLU"],
    "VID": ["SEQN", "LBXVIDMS"],
    "VIC": ["SEQN", "LBXVIC", "LBDVICSI"],
    "FOLATE": ["SEQN", "LBDRFO"],
    "FERTIN": ["SEQN", "LBXFER"],
    "VITB12": ["SEQN", "LBXB12", "LBDB12", "LBDB12SI"],
    "THYROD": ["SEQN", "LBXTSH1", "LBDTSH1S"],
    "DR1TOT": [
        "SEQN",
        "DR1DRSTZ",
        "DR1TKCAL",
        "DR1TPROT",
        "DR1TVB12",
        "DR1TVC",
        "DR1TVD",
        "DR1TCALC",
        "DR1TMAGN",
        "DR1TIRON",
        "DR1TZINC",
        "DR1TFDFE",
        "DR1TP183",
        "DR1TP205",
        "DR1TP225",
        "DR1TP226",
    ],
}


def first_value(row: pd.Series, *columns: str) -> Any:
    for column in columns:
        if column in row.index:
            value = row.get(column)
            if safe_float(value) is not None:
                return value
    return None


def download_file(config: CycleConfig, stem: str, force: bool = False) -> tuple[Path | None, dict[str, Any]]:
    config.raw_dir.mkdir(parents=True, exist_ok=True)
    file_code = config.file_code(stem)
    path = config.raw_dir / f"{file_code}.XPT"
    url = f"{config.base_url}/{file_code}.XPT"
    row: dict[str, Any] = {
        "cycle": config.cycle,
        "file_code": file_code,
        "stem": stem,
        "description": config.files[stem],
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
        with urlopen(Request(url, headers={"User-Agent": "SupleMatch-MVP/1.0"}), timeout=120) as response:
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


def read_xpt(path: Path, columns: list[str]) -> pd.DataFrame:
    frame = pd.read_sas(path, format="xport", encoding="utf-8")
    present = [column for column in columns if column in frame.columns]
    return frame[present]


def merge_cycle(config: CycleConfig, files: dict[str, Path]) -> pd.DataFrame:
    merged: pd.DataFrame | None = None
    for stem, path in files.items():
        columns = COLUMN_MAP.get(stem)
        if not columns:
            continue
        frame = read_xpt(path, columns)
        if "SEQN" not in frame.columns:
            continue
        frame = frame.drop_duplicates(subset=["SEQN"])
        merged = frame if merged is None else merged.merge(frame, on="SEQN", how="left")
    if merged is None or merged.empty:
        raise RuntimeError(f"No se pudo unir ciclo NHANES {config.cycle}")
    merged["benchmark_nhanes_cycle"] = config.cycle
    return merged


def nutrient_status(value: Any, *, low: float, critical_low: float | None = None) -> str:
    return status_low_high(value, low=low, critical_low=critical_low)


def diet_zinc_status(value: Any, sexo: str) -> str:
    return nutrient_status(value, low=8 if sexo == "F" else 11)


def diet_magnesium_status(value: Any, sexo: str, age: float) -> str:
    if sexo == "F":
        low = 320 if age >= 31 else 310
    else:
        low = 420 if age >= 31 else 400
    return nutrient_status(value, low=low)


def diet_protein_status(protein: Any, weight: Any) -> str:
    protein_value = safe_float(protein)
    weight_value = safe_float(weight)
    if protein_value is None or weight_value is None or weight_value <= 0:
        return "missing"
    target = 0.8 * weight_value
    if protein_value < target * 0.65:
        return "critical_low"
    if protein_value < target:
        return "low"
    return "normal"


def diet_omega3_status(row: pd.Series) -> str:
    epa = safe_float(first_value(row, "DR1TP205")) or 0.0
    dpa = safe_float(first_value(row, "DR1TP225")) or 0.0
    dha = safe_float(first_value(row, "DR1TP226")) or 0.0
    total_marine = epa + dpa + dha
    if safe_float(first_value(row, "DR1TP205", "DR1TP225", "DR1TP226")) is None:
        return "missing"
    if total_marine < 0.05:
        return "critical_low"
    if total_marine < 0.25:
        return "low"
    return "normal"


def tsh_status(value: Any) -> str:
    return status_low_high(value, low=0.4, critical_low=0.1, high=4.5, critical_high=10.0)


def b12_status(value: Any) -> str:
    return status_low_high(value, low=200, critical_low=150)


def source_case_id(cycle: str, seqn: Any) -> str:
    number = int(float(seqn))
    return f"NHANES-{cycle}-{number}"


def hash_case_id(source_id: str, salt: str) -> str:
    digest = hashlib.sha256(f"{salt}:{source_id}".encode("utf-8")).hexdigest()
    return f"nhanes_{digest[:20]}"


def row_to_features(row: pd.Series, salt: str, generated_at: str) -> dict[str, Any] | None:
    seqn = safe_float(row.get("SEQN"))
    age = safe_float(row.get("RIDAGEYR"))
    weight = safe_float(row.get("BMXWT"))
    height = safe_float(row.get("BMXHT"))
    bmi = safe_float(row.get("BMXBMI"))
    cycle = str(row.get("benchmark_nhanes_cycle", "unknown"))
    if seqn is None or age is None or age < 18 or weight is None or height is None or bmi is None:
        return None

    sexo = "M" if safe_float(row.get("RIAGENDR")) == 1 else "F"
    egfr = egfr_2021_creatinine(row.get("LBXSCR"), age, sexo)
    b12_value = first_value(row, "LBXB12", "LBDB12")
    source_id = source_case_id(cycle, seqn)
    protein = first_value(row, "DR1TPROT")
    partial_features = {
        "sexo": sexo,
        "tipo_dieta": "unknown",
        "exposicion_solar": "unknown",
        "nivel_actividad": "unknown",
        "lab_panel_source": "nhanes_multi_cycle_public_xpt",
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
        "protein_g_day_estimate": round(float(protein), 2) if safe_float(protein) is not None else -1.0,
        "lab_vitamin_d_status": status_low_high(row.get("LBXVIDMS"), low=50, critical_low=30),
        "lab_b12_status": b12_status(b12_value),
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
        "lab_creatinine_status": status_low_high(row.get("LBXSCR"), high=1.1 if sexo == "F" else 1.3, critical_high=2.0),
        "lab_egfr_status": egfr_status(egfr),
        "lab_alt_status": status_low_high(row.get("LBXSATSI"), high=40, critical_high=120),
        "lab_ast_status": status_low_high(row.get("LBXSASSI"), high=40, critical_high=120),
        "lab_tsh_status": tsh_status(row.get("LBXTSH1")),
    }
    prepared = _prepare_features(partial_features, CAT_COLS, NUM_COLS)
    normalized = {
        "generated_at": generated_at,
        "case_id": hash_case_id(source_id, salt),
        "collected_at": cycle.replace("_", "-"),
        "data_source": f"CDC NHANES public-use {cycle.replace('_', '-')}",
        "reviewer_code": "unreviewed_public_dataset",
        "expected_positive": "",
        "expected_negative": "",
    }
    for column in CAT_COLS + NUM_COLS:
        normalized[column] = prepared[column]

    normalized.update(
        {
            "benchmark_nhanes_cycle": cycle,
            "benchmark_lab_vitamin_c_status": status_low_high(row.get("LBDVICSI"), low=23, critical_low=11.4),
            "benchmark_lab_vitamin_c_observed": int(status_low_high(row.get("LBDVICSI"), low=23, critical_low=11.4) != "missing"),
            "benchmark_diet_b12_status": nutrient_status(row.get("DR1TVB12"), low=2.4, critical_low=1.2),
            "benchmark_diet_vitamin_c_status": nutrient_status(row.get("DR1TVC"), low=75 if sexo == "F" else 90, critical_low=30),
            "benchmark_diet_zinc_status": diet_zinc_status(row.get("DR1TZINC"), sexo),
            "benchmark_diet_magnesium_status": diet_magnesium_status(row.get("DR1TMAGN"), sexo, age),
            "benchmark_diet_calcium_status": nutrient_status(row.get("DR1TCALC"), low=1000),
            "benchmark_diet_folate_status": nutrient_status(row.get("DR1TFDFE"), low=400, critical_low=200),
            "benchmark_diet_protein_status": diet_protein_status(protein, weight),
            "benchmark_diet_omega3_status": diet_omega3_status(row),
            "benchmark_diet_record_status": int(safe_float(row.get("DR1DRSTZ")) == 1),
            "benchmark_diet_energy_kcal": round(float(first_value(row, "DR1TKCAL")), 2) if safe_float(first_value(row, "DR1TKCAL")) is not None else "",
            "benchmark_diet_protein_g": round(float(protein), 2) if safe_float(protein) is not None else "",
            "benchmark_diet_b12_mcg": round(float(first_value(row, "DR1TVB12")), 2) if safe_float(first_value(row, "DR1TVB12")) is not None else "",
            "benchmark_diet_vitamin_c_mg": round(float(first_value(row, "DR1TVC")), 2) if safe_float(first_value(row, "DR1TVC")) is not None else "",
            "benchmark_diet_zinc_mg": round(float(first_value(row, "DR1TZINC")), 2) if safe_float(first_value(row, "DR1TZINC")) is not None else "",
            "benchmark_diet_magnesium_mg": round(float(first_value(row, "DR1TMAGN")), 2) if safe_float(first_value(row, "DR1TMAGN")) is not None else "",
            "benchmark_diet_epa_dpa_dha_g": round(
                (safe_float(first_value(row, "DR1TP205")) or 0.0)
                + (safe_float(first_value(row, "DR1TP225")) or 0.0)
                + (safe_float(first_value(row, "DR1TP226")) or 0.0),
                3,
            )
            if safe_float(first_value(row, "DR1TP205", "DR1TP225", "DR1TP226")) is not None
            else "",
        }
    )
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


def run(args: argparse.Namespace) -> None:
    generated_at = utc_now()
    salt = args.salt or os.getenv("NHANES_CASE_HASH_SALT") or "suplematch-nhanes-public-demo-salt"
    cycle_names = [item.strip() for item in args.cycles.split(",") if item.strip()]
    unknown_cycles = sorted(set(cycle_names) - set(CYCLES))
    if unknown_cycles:
        raise SystemExit(f"Ciclos NHANES no soportados: {', '.join(unknown_cycles)}")

    manifest: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []
    merged_rows = 0
    cycle_case_counts: dict[str, int] = {}
    for cycle_name in cycle_names:
        config = CYCLES[cycle_name]
        files: dict[str, Path] = {}
        for stem in config.files:
            path, row = download_file(config, stem, force=args.force_download)
            manifest.append(row)
            if path is not None:
                files[stem] = path
        required = {"DEMO", "BMX"}
        missing_required = sorted(required - set(files))
        if missing_required:
            raise SystemExit(f"Faltan archivos requeridos para {cycle_name}: {', '.join(missing_required)}")
        merged = merge_cycle(config, files)
        merged_rows += len(merged)
        cycle_count = 0
        for _, row in merged.iterrows():
            normalized = row_to_features(row, salt=salt, generated_at=generated_at)
            if normalized:
                cases.append(normalized)
                cycle_count += 1
            if args.limit_per_cycle and cycle_count >= args.limit_per_cycle:
                break
        cycle_case_counts[cycle_name] = cycle_count

    if not cases:
        raise SystemExit("No se generaron casos NHANES multi-ciclo validos.")

    knowledge = load_knowledge()
    labels = knowledge["conditions"]["labels"]
    predictions = prediction_rows(cases, generated_at=generated_at)
    condition_summary = summarize_conditions(predictions)

    output_path = Path(args.output)
    predictions_path = Path(args.predictions)
    summary_path = Path(args.summary)
    condition_summary_path = Path(args.condition_summary)
    source_manifest_path = Path(args.source_manifest)
    for path in [output_path, predictions_path, summary_path, condition_summary_path, source_manifest_path]:
        path.parent.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(cases).to_csv(output_path, index=False)
    pd.DataFrame(predictions).to_csv(predictions_path, index=False)
    pd.DataFrame(condition_summary).to_csv(condition_summary_path, index=False)
    pd.DataFrame(manifest).to_csv(source_manifest_path, index=False)
    pd.DataFrame(
        [
            {
                "generated_at": generated_at,
                "source": "CDC NHANES public-use multi-cycle",
                "source_page": "https://wwwn.cdc.gov/nchs/nhanes/",
                "cycles": "|".join(cycle_names),
                "raw_component_files": sum(1 for row in manifest if row["status"] in {"cached", "downloaded"}),
                "merged_rows": merged_rows,
                "accepted_cases": len(cases),
                "prediction_rows": len(predictions),
                "condition_labels": len(labels),
                "minimum_age": 18,
                "seqn_in_output": False,
                "cycle_case_counts": "|".join(f"{cycle}:{count}" for cycle, count in cycle_case_counts.items()),
                "salt_source": "arg_or_env" if args.salt or os.getenv("NHANES_CASE_HASH_SALT") else "local_default_demo_only",
                "output_path": rel(output_path),
                "predictions_path": rel(predictions_path),
                "condition_summary_path": rel(condition_summary_path),
                "source_manifest_path": rel(source_manifest_path),
                "clinical_validation": "not_clinically_validated",
            }
        ]
    ).to_csv(summary_path, index=False)

    print("Importacion NHANES multi-ciclo condition_mvp completada")
    print(f"  ciclos: {', '.join(cycle_names)}")
    print(f"  casos aceptados: {len(cases)}")
    print(f"  predicciones: {len(predictions)}")
    print(f"  output: {output_path}")
    print(f"  resumen: {summary_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Importa varios ciclos NHANES como benchmark anonimo para condition_mvp.")
    parser.add_argument("--cycles", default="2011_2012,2013_2014,2015_2016,2017_2018", help="Ciclos separados por coma.")
    parser.add_argument("--limit-per-cycle", type=int, default=500, help="Casos adultos maximos por ciclo. 0 = todos.")
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
