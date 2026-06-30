#!/usr/bin/env python3
"""
Pipeline MVP auditable para modelo de condiciones probables.

Etapas:
1. Carga y auditoria de fuentes oficiales.
2. Validacion/limpieza de conocimiento medico curado.
3. EDA de reglas, biomarcadores y cobertura de fuentes.
4. Generacion de dataset semisintetico trazable.
5. Entrenamiento multilabel calibrado.
6. Reportes y artefactos versionados.

El modelo estima probabilidades de riesgo/prioridad. No diagnostica.
"""

from __future__ import annotations

import argparse
import math
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    hamming_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.multiclass import OneVsRestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


ROOT_DIR = Path(__file__).resolve().parents[2]
KNOWLEDGE_DIR = ROOT_DIR / "data/knowledge"
TRAINING_DIR = ROOT_DIR / "data/training/condition_model"
REPORT_DIR = ROOT_DIR / "data/reports/condition_model"
RUNTIME_DIR = ROOT_DIR / "models/runtime"

LAB_STATUS_COLS = [
    "lab_vitamin_d_status",
    "lab_b12_status",
    "lab_ferritin_status",
    "lab_hemoglobin_status",
    "lab_magnesium_status",
    "lab_zinc_status",
    "lab_calcium_status",
    "lab_folate_status",
    "lab_glucose_status",
    "lab_total_cholesterol_status",
    "lab_ldl_status",
    "lab_hdl_status",
    "lab_triglycerides_status",
    "lab_creatinine_status",
    "lab_egfr_status",
    "lab_alt_status",
    "lab_ast_status",
    "lab_tsh_status",
]

LAB_BASES = [col.removeprefix("lab_").removesuffix("_status") for col in LAB_STATUS_COLS]

SYMPTOM_COLS = [
    "fatiga_general",
    "dolor_muscular",
    "dolor_articular",
    "niebla_mental",
    "problemas_sueno",
    "caida_cabello",
    "piel_seca",
    "unas_quebradizas",
    "enfermedad_frecuente",
    "calambres",
    "irritabilidad",
]

DIET_QUANTITY_COLS = [
    "fish_servings_week",
    "dairy_servings_day",
    "legume_servings_week",
    "meat_servings_week",
    "fruit_veg_servings_day",
    "protein_g_day_estimate",
]

DIET_META_COLS = [f"{col}_reported" for col in DIET_QUANTITY_COLS] + ["diet_quantity_missing_count"]

SOFT_SIGNAL_COLS = [
    "vitamin_c_diet_signal",
    "protein_insufficient_signal",
    "protein_gap_g_day",
    "hair_skin_nails_cluster",
]

BENCHMARK_STATUS_COLS = [
    "benchmark_lab_vitamin_c_status",
    "benchmark_diet_b12_status",
    "benchmark_diet_vitamin_c_status",
    "benchmark_diet_zinc_status",
    "benchmark_diet_magnesium_status",
    "benchmark_diet_calcium_status",
    "benchmark_diet_folate_status",
    "benchmark_diet_protein_status",
    "benchmark_diet_omega3_status",
]

LAB_META_COLS = [
    item
    for base in LAB_BASES
    for item in (
        f"lab_{base}_observed",
        f"lab_{base}_age_days",
        f"lab_{base}_unit_known",
        f"lab_{base}_range_known",
    )
]

CAT_COLS = [
    "sexo",
    "tipo_dieta",
    "exposicion_solar",
    "nivel_actividad",
    "lab_panel_source",
] + LAB_STATUS_COLS + BENCHMARK_STATUS_COLS

NUM_COLS = [
    "edad",
    "peso_kg",
    "altura_cm",
    "bmi",
    "fatiga_general",
    "dolor_muscular",
    "dolor_articular",
    "niebla_mental",
    "problemas_sueno",
    "caida_cabello",
    "piel_seca",
    "unas_quebradizas",
    "enfermedad_frecuente",
    "calambres",
    "irritabilidad",
    "dieta_deficiente",
    "estres_alto",
    "meta_energia",
    "meta_inmunidad",
    "meta_belleza",
    "meta_rendimiento",
    "meta_salud_osea",
    "meta_cognitivo",
    "symptom_burden_score",
    "high_symptom_count",
    "observed_lab_count",
    "missing_lab_count",
] + DIET_QUANTITY_COLS + DIET_META_COLS + SOFT_SIGNAL_COLS + LAB_META_COLS


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, keep_default_na=False)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def split_values(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    return [item.strip() for item in text.split("|") if item.strip()]


def parse_rule_value(value: Any, operator: str) -> Any:
    values = split_values(value)
    if operator == "in":
        return values
    text = str(value or "").strip()
    try:
        number = float(text)
    except ValueError:
        return text
    if number.is_integer():
        return int(number)
    return number


def parse_optional_float(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    return float(text)


def load_knowledge() -> dict[str, Any]:
    sources_df = read_csv(KNOWLEDGE_DIR / "sources.csv")
    domains_df = read_csv(KNOWLEDGE_DIR / "source_domains.csv")
    conditions_df = read_csv(KNOWLEDGE_DIR / "conditions.csv")
    rules_df = read_csv(KNOWLEDGE_DIR / "condition_rules.csv")
    biomarkers_df = read_csv(KNOWLEDGE_DIR / "biomarkers.csv")
    links_df = read_csv(KNOWLEDGE_DIR / "condition_component_links.csv")
    safety_df = read_csv(KNOWLEDGE_DIR / "safety_rules.csv")
    requirements_df = read_csv(KNOWLEDGE_DIR / "condition_data_requirements.csv")

    source_version = str(sources_df["version"].iloc[0])
    condition_version = str(conditions_df["version"].iloc[0])

    condition_rules: dict[str, list[dict[str, Any]]] = {}
    for row in rules_df.to_dict("records"):
        operator = str(row["operator"])
        condition_rules.setdefault(str(row["condition_code"]), []).append(
            {
                "field": str(row["field"]),
                "operator": operator,
                "value": parse_rule_value(row["value"], operator),
                "weight": float(row["weight"]),
            }
        )

    conditions = []
    for row in conditions_df.to_dict("records"):
        code = str(row["condition_code"])
        conditions.append(
            {
                "code": code,
                "display_name": str(row["display_name"]),
                "positive_threshold": float(row["positive_threshold"]),
                "source_ids": split_values(row["source_ids"]),
                "rules": condition_rules.get(code, []),
            }
        )

    return {
        "sources": {
            "version": source_version,
            "allowed_domains": [str(row["domain"]) for row in domains_df.to_dict("records")],
            "sources": [
                {
                    "id": str(row["source_id"]),
                    "title": str(row["title"]),
                    "organization": str(row["organization"]),
                    "url": str(row["url"]),
                    "used_for": split_values(row["used_for"]),
                }
                for row in sources_df.to_dict("records")
            ],
        },
        "conditions": {
            "version": condition_version,
            "labels": [str(row["condition_code"]) for row in conditions_df.to_dict("records")],
            "conditions": conditions,
        },
        "biomarkers": {
            "version": str(biomarkers_df["version"].iloc[0]),
            "biomarkers": [
                {
                    "code": str(row["biomarker_code"]),
                    "display_name": str(row["display_name"]),
                    "unit": str(row["unit"]),
                    "low": parse_optional_float(row["low"]),
                    "borderline": parse_optional_float(row["borderline"]),
                    "critical_low": parse_optional_float(row["critical_low"]),
                    "high": parse_optional_float(row["high"]),
                    "critical_high": parse_optional_float(row["critical_high"]),
                    "condition_code": str(row["condition_code"] or ""),
                    "safety_condition": str(row["safety_condition"] or ""),
                    "source_ids": split_values(row["source_ids"]),
                }
                for row in biomarkers_df.to_dict("records")
            ],
        },
        "links": {
            "version": str(links_df["version"].iloc[0]),
            "links": [
                {
                    "condition_code": str(row["condition_code"]),
                    "component": str(row["component"]),
                    "evidence_strength": str(row["evidence_strength"]),
                    "source_ids": split_values(row["source_ids"]),
                }
                for row in links_df.to_dict("records")
            ],
        },
        "safety": {
            "version": str(safety_df["version"].iloc[0]),
            "rules": [
                {
                    "code": str(row["rule_code"]),
                    "condition": {
                        "field": str(row["field"]),
                        "operator": str(row["operator"]),
                        "value": parse_rule_value(row["value"], str(row["operator"])),
                    },
                    "action": str(row["action"]),
                    "severity": str(row["severity"]),
                    "message": str(row["message"]),
                    "source_ids": split_values(row["source_ids"]),
                }
                for row in safety_df.to_dict("records")
            ],
        },
        "requirements": {
            "items": [
                {
                    "condition_code": str(row["condition_code"]),
                    "kind": str(row["kind"]),
                    "needs_survey_fields": split_values(row["needs_survey_fields"]),
                    "needs_lab_fields": split_values(row["needs_lab_fields"]),
                    "needs_safety_fields": split_values(row["needs_safety_fields"]),
                    "interpretation": str(row["interpretation"]),
                }
                for row in requirements_df.to_dict("records")
            ],
        },
    }


def audit_sources(knowledge: dict[str, Any]) -> dict[str, Any]:
    allowed_domains = set(knowledge["sources"]["allowed_domains"])
    sources = knowledge["sources"]["sources"]
    ids = [source["id"] for source in sources]
    duplicate_ids = sorted({source_id for source_id in ids if ids.count(source_id) > 1})

    invalid = []
    for source in sources:
        domain = urlparse(source["url"]).netloc.lower().replace("www.", "")
        if not any(domain == allowed or domain.endswith(f".{allowed}") for allowed in allowed_domains):
            invalid.append({"id": source["id"], "url": source["url"], "domain": domain})

    report = {
        "generated_at": utc_now(),
        "source_count": len(sources),
        "allowed_domains": sorted(allowed_domains),
        "duplicate_ids": duplicate_ids,
        "invalid_domains": invalid,
        "sources": [
            {
                "id": source["id"],
                "organization": source["organization"],
                "url": source["url"],
                "used_for": source.get("used_for", []),
            }
            for source in sources
        ],
    }
    if duplicate_ids or invalid:
        raise ValueError(f"Auditoria de fuentes fallida: duplicates={duplicate_ids}, invalid={invalid}")
    return report


def validate_knowledge(knowledge: dict[str, Any]) -> dict[str, Any]:
    source_ids = {source["id"] for source in knowledge["sources"]["sources"]}
    labels = knowledge["conditions"]["labels"]
    condition_codes = {condition["code"] for condition in knowledge["conditions"]["conditions"]}
    feature_columns = set(CAT_COLS + NUM_COLS)

    errors = []
    for condition in knowledge["conditions"]["conditions"]:
        if condition["code"] not in labels:
            errors.append(f"condition_not_in_labels:{condition['code']}")
        for source_id in condition.get("source_ids", []):
            if source_id not in source_ids:
                errors.append(f"missing_source:{condition['code']}:{source_id}")
        for rule in condition.get("rules", []):
            if "field" not in rule or "operator" not in rule or "weight" not in rule:
                errors.append(f"invalid_rule:{condition['code']}:{rule}")
            elif rule["field"] not in feature_columns:
                errors.append(f"unknown_rule_field:{condition['code']}:{rule['field']}")

    for biomarker in knowledge["biomarkers"]["biomarkers"]:
        for source_id in biomarker.get("source_ids", []):
            if source_id not in source_ids:
                errors.append(f"missing_source:{biomarker['code']}:{source_id}")

    for link in knowledge["links"]["links"]:
        if link["condition_code"] not in condition_codes:
            errors.append(f"link_unknown_condition:{link['condition_code']}")
        for source_id in link.get("source_ids", []):
            if source_id not in source_ids:
                errors.append(f"missing_source:{link['condition_code']}:{source_id}")

    for rule in knowledge["safety"]["rules"]:
        for source_id in rule.get("source_ids", []):
            if source_id not in source_ids:
                errors.append(f"missing_source:{rule['code']}:{source_id}")

    if errors:
        raise ValueError("Conocimiento medico invalido: " + ", ".join(errors[:20]))

    return {
        "generated_at": utc_now(),
        "condition_count": len(condition_codes),
        "label_count": len(labels),
        "biomarker_count": len(knowledge["biomarkers"]["biomarkers"]),
        "condition_component_link_count": len(knowledge["links"]["links"]),
        "safety_rule_count": len(knowledge["safety"]["rules"]),
        "rules_by_condition": {
            condition["code"]: len(condition.get("rules", []))
            for condition in knowledge["conditions"]["conditions"]
        },
        "sources_by_condition": {
            condition["code"]: condition.get("source_ids", [])
            for condition in knowledge["conditions"]["conditions"]
        },
    }


def weighted_choice(rng: random.Random, choices: list[tuple[Any, float]]) -> Any:
    values, weights = zip(*choices)
    return rng.choices(values, weights=weights, k=1)[0]


def severity_from_choices(rng: random.Random, high_probability: float = 0.22) -> int:
    if rng.random() < high_probability:
        return rng.choice([4, 5])
    return weighted_choice(rng, [(1, 0.28), (2, 0.28), (3, 0.24), (4, 0.14), (5, 0.06)])


def lab_status(rng: random.Random, low_probability: float, critical_probability: float = 0.03) -> str:
    roll = rng.random()
    if roll < critical_probability:
        return "critical_low"
    if roll < low_probability:
        return "low"
    if roll < low_probability + 0.08:
        return "borderline"
    if roll < 0.72:
        return "normal"
    return "missing"


def diet_status_from_signal(rng: random.Random, risk_probability: float, critical_probability: float = 0.04) -> str:
    roll = rng.random()
    if roll < critical_probability:
        return "critical_low"
    if roll < risk_probability:
        return "low"
    if roll < risk_probability + 0.05:
        return "borderline"
    if roll < 0.92:
        return "normal"
    return "missing"


def high_lab_status(rng: random.Random, high_probability: float, critical_probability: float = 0.03) -> str:
    roll = rng.random()
    if roll < critical_probability:
        return "critical_high"
    if roll < high_probability:
        return "high"
    if roll < high_probability + 0.08:
        return "borderline"
    if roll < 0.72:
        return "normal"
    return "missing"


def thyroid_status(rng: random.Random, altered_probability: float = 0.12) -> str:
    roll = rng.random()
    if roll < 0.015:
        return "critical_low"
    if roll < altered_probability / 2:
        return "low"
    if roll < altered_probability:
        return "high"
    if roll < altered_probability + 0.015:
        return "critical_high"
    if roll < altered_probability + 0.08:
        return "borderline"
    if roll < 0.72:
        return "normal"
    return "missing"


def bounded_gauss(rng: random.Random, mean: float, std: float, min_value: float, max_value: float) -> float:
    return round(max(min_value, min(max_value, rng.gauss(mean, std))), 2)


def build_diet_quantities(rng: random.Random, tipo_dieta: str, nivel_actividad: str, peso_kg: float) -> dict[str, Any]:
    if tipo_dieta == "vegano":
        fish = 0.0
        dairy = 0.0
        meat = 0.0
        legumes = bounded_gauss(rng, 4.5, 2.0, 0.0, 14.0)
    elif tipo_dieta == "vegetariano":
        fish = 0.0
        dairy = bounded_gauss(rng, 1.0, 0.7, 0.0, 4.0)
        meat = 0.0
        legumes = bounded_gauss(rng, 3.8, 1.8, 0.0, 14.0)
    elif tipo_dieta == "pescetariano":
        fish = bounded_gauss(rng, 2.2, 1.2, 0.0, 7.0)
        dairy = bounded_gauss(rng, 1.1, 0.8, 0.0, 4.0)
        meat = 0.0
        legumes = bounded_gauss(rng, 2.2, 1.4, 0.0, 14.0)
    else:
        fish = bounded_gauss(rng, 1.0, 0.9, 0.0, 7.0)
        dairy = bounded_gauss(rng, 1.2, 0.8, 0.0, 4.0)
        meat = bounded_gauss(rng, 3.2, 1.8, 0.0, 14.0)
        legumes = bounded_gauss(rng, 1.8, 1.3, 0.0, 14.0)

    activity_factor = 1.45 if nivel_actividad in {"activo", "muy_activo"} else 1.05
    diet_factor = 0.72 if tipo_dieta in {"vegano", "vegetariano"} else 0.95
    protein = bounded_gauss(rng, peso_kg * activity_factor * diet_factor, 14.0, 25.0, 190.0)

    return {
        "fish_servings_week": fish,
        "dairy_servings_day": dairy,
        "legume_servings_week": legumes,
        "meat_servings_week": meat,
        "fruit_veg_servings_day": bounded_gauss(rng, 3.0 if tipo_dieta in {"vegano", "vegetariano"} else 2.4, 1.5, 0.0, 10.0),
        "protein_g_day_estimate": protein,
    }


def attach_diet_metadata(row: dict[str, Any], rng: random.Random) -> None:
    missing_count = 0
    for col in DIET_QUANTITY_COLS:
        reported = 1 if rng.random() > 0.12 else 0
        if not reported:
            row[col] = -1.0
            missing_count += 1
        row[f"{col}_reported"] = reported
    row["diet_quantity_missing_count"] = missing_count


def attach_benchmark_status_features(row: dict[str, Any], rng: random.Random) -> None:
    fish = float(row.get("fish_servings_week", -1))
    dairy = float(row.get("dairy_servings_day", -1))
    legumes = float(row.get("legume_servings_week", -1))
    meat = float(row.get("meat_servings_week", -1))
    fruit_veg = float(row.get("fruit_veg_servings_day", -1))
    protein = float(row.get("protein_g_day_estimate", -1))
    tipo_dieta = row.get("tipo_dieta")
    peso_kg = float(row.get("peso_kg", 70.0))

    def status_from_reported(value: float, risk: float, critical: float = 0.04) -> str:
        if value < 0:
            return "missing"
        return diet_status_from_signal(rng, risk_probability=risk, critical_probability=critical)

    b12_risk = 0.72 if tipo_dieta == "vegano" else 0.50 if tipo_dieta == "vegetariano" else 0.28 if meat <= 1 else 0.08
    vitamin_c_risk = 0.70 if fruit_veg >= 0 and fruit_veg <= 2 else 0.12
    zinc_risk = 0.62 if meat <= 1 and legumes <= 2 else 0.28 if int(row.get("dieta_deficiente", 0)) else 0.08
    magnesium_risk = 0.62 if legumes <= 1 or int(row.get("calambres", 0)) >= 4 else 0.16
    calcium_risk = 0.68 if dairy <= 1 else 0.14
    folate_risk = 0.62 if legumes <= 1 and fruit_veg <= 2 else 0.12
    omega3_risk = 0.82 if fish <= 1 else 0.18
    protein_target = 0.8 * peso_kg
    protein_risk = 0.82 if protein >= 0 and protein < protein_target else 0.12

    row["benchmark_diet_b12_status"] = status_from_reported(meat, b12_risk, critical=0.08 if tipo_dieta == "vegano" else 0.03)
    row["benchmark_diet_vitamin_c_status"] = status_from_reported(fruit_veg, vitamin_c_risk)
    row["benchmark_diet_zinc_status"] = status_from_reported(meat + legumes, zinc_risk)
    row["benchmark_diet_magnesium_status"] = status_from_reported(legumes, magnesium_risk)
    row["benchmark_diet_calcium_status"] = status_from_reported(dairy, calcium_risk)
    row["benchmark_diet_folate_status"] = status_from_reported(legumes + fruit_veg, folate_risk)
    row["benchmark_diet_protein_status"] = status_from_reported(protein, protein_risk, critical=0.07)
    row["benchmark_diet_omega3_status"] = status_from_reported(fish, omega3_risk, critical=0.10)
    row["benchmark_lab_vitamin_c_status"] = lab_status(
        rng,
        low_probability=0.42 if row["benchmark_diet_vitamin_c_status"] in {"low", "critical_low"} else 0.08,
        critical_probability=0.06 if row["benchmark_diet_vitamin_c_status"] == "critical_low" else 0.015,
    )


def attach_lab_metadata(row: dict[str, Any], rng: random.Random) -> None:
    observed_count = 0
    for status_col in LAB_STATUS_COLS:
        base = status_col.removeprefix("lab_").removesuffix("_status")
        observed = 0 if row.get(status_col) == "missing" else 1
        observed_count += observed
        row[f"lab_{base}_observed"] = observed
        row[f"lab_{base}_age_days"] = rng.randint(1, 120) if observed else 999
        row[f"lab_{base}_unit_known"] = 1 if observed and rng.random() < 0.96 else 0
        row[f"lab_{base}_range_known"] = 1 if observed and rng.random() < 0.78 else 0
    row["observed_lab_count"] = observed_count
    row["missing_lab_count"] = len(LAB_STATUS_COLS) - observed_count
    if observed_count == 0:
        row["lab_panel_source"] = "none"
    else:
        row["lab_panel_source"] = weighted_choice(rng, [("ocr_pdf", 0.55), ("ocr_photo", 0.25), ("manual", 0.20)])


def attach_soft_signal_features(row: dict[str, Any]) -> None:
    fruit_veg_reported = int(row.get("fruit_veg_servings_day_reported", 0))
    fruit_veg = float(row.get("fruit_veg_servings_day", -1))
    row["vitamin_c_diet_signal"] = int(
        bool(fruit_veg_reported)
        and fruit_veg <= 2
        and (
            int(row.get("dieta_deficiente", 0)) == 1
            or int(row.get("enfermedad_frecuente", 0)) >= 4
            or int(row.get("meta_inmunidad", 0)) == 1
        )
    )

    protein_reported = int(row.get("protein_g_day_estimate_reported", 0))
    protein = float(row.get("protein_g_day_estimate", -1))
    activity_multiplier = 1.2 if row.get("nivel_actividad") in {"activo", "muy_activo"} else 0.85
    protein_target = float(row.get("peso_kg", 70.0)) * activity_multiplier
    if protein_reported:
        protein_gap = max(0.0, protein_target - protein)
    else:
        protein_gap = -1.0
    row["protein_gap_g_day"] = round(protein_gap, 2)
    row["protein_insufficient_signal"] = int(
        bool(protein_reported)
        and (
            protein < 55
            or protein_gap >= 20
            or (
                row.get("nivel_actividad") in {"activo", "muy_activo"}
                and protein_gap >= 12
                and int(row.get("meta_rendimiento", 0)) == 1
            )
        )
    )

    hair_skin_hits = [
        int(row.get("meta_belleza", 0)) == 1,
        int(row.get("caida_cabello", 0)) >= 4,
        int(row.get("piel_seca", 0)) >= 4,
        int(row.get("unas_quebradizas", 0)) >= 4,
        row.get("lab_zinc_status") in {"low", "critical_low"},
        row.get("benchmark_diet_zinc_status") in {"low", "critical_low"},
        row.get("lab_ferritin_status") in {"low", "critical_low"},
    ]
    row["hair_skin_nails_cluster"] = sum(1 for hit in hair_skin_hits if hit)


def build_synthetic_row(rng: random.Random) -> dict[str, Any]:
    sexo = weighted_choice(rng, [("F", 0.52), ("M", 0.48)])
    edad = int(round(min(78, max(16, rng.gauss(35, 14)))))
    altura_cm = round(rng.gauss(162 if sexo == "F" else 171, 8), 1)
    peso_kg = round(max(42, min(120, rng.gauss(68 if sexo == "F" else 78, 14))), 1)
    bmi = round(peso_kg / ((altura_cm / 100) ** 2), 2)
    tipo_dieta = weighted_choice(
        rng,
        [("omnivoro", 0.68), ("pescetariano", 0.08), ("vegetariano", 0.15), ("vegano", 0.09)],
    )
    exposicion_solar = weighted_choice(rng, [("baja", 0.34), ("media", 0.48), ("alta", 0.18)])
    nivel_actividad = weighted_choice(
        rng,
        [("sedentario", 0.28), ("moderado", 0.36), ("activo", 0.24), ("muy_activo", 0.12)],
    )
    dieta_deficiente = 1 if tipo_dieta in {"vegano", "vegetariano"} or rng.random() < 0.32 else 0
    estres_alto = 1 if rng.random() < 0.34 else 0
    problemas_sueno = severity_from_choices(rng, 0.30 if estres_alto else 0.18)
    irritabilidad = severity_from_choices(rng, 0.34 if estres_alto else 0.16)
    fatiga_general = severity_from_choices(rng, 0.30 if problemas_sueno >= 4 or dieta_deficiente else 0.18)

    row = {
        "sexo": sexo,
        "tipo_dieta": tipo_dieta,
        "exposicion_solar": exposicion_solar,
        "nivel_actividad": nivel_actividad,
        "edad": edad,
        "peso_kg": peso_kg,
        "altura_cm": altura_cm,
        "bmi": bmi,
        "fatiga_general": fatiga_general,
        "dolor_muscular": severity_from_choices(rng, 0.30 if nivel_actividad in {"activo", "muy_activo"} else 0.16),
        "dolor_articular": severity_from_choices(rng, 0.18),
        "niebla_mental": severity_from_choices(rng, 0.28 if problemas_sueno >= 4 else 0.14),
        "problemas_sueno": problemas_sueno,
        "caida_cabello": severity_from_choices(rng, 0.20),
        "piel_seca": severity_from_choices(rng, 0.18),
        "unas_quebradizas": severity_from_choices(rng, 0.16),
        "enfermedad_frecuente": severity_from_choices(rng, 0.26 if dieta_deficiente else 0.16),
        "calambres": severity_from_choices(rng, 0.25 if nivel_actividad in {"activo", "muy_activo"} else 0.16),
        "irritabilidad": irritabilidad,
        "dieta_deficiente": dieta_deficiente,
        "estres_alto": estres_alto,
        "meta_energia": 1 if fatiga_general >= 4 or rng.random() < 0.20 else 0,
        "meta_inmunidad": 1 if rng.random() < 0.18 else 0,
        "meta_belleza": 1 if rng.random() < 0.17 else 0,
        "meta_rendimiento": 1 if nivel_actividad in {"activo", "muy_activo"} and rng.random() < 0.40 else 0,
        "meta_salud_osea": 1 if edad >= 50 or rng.random() < 0.14 else 0,
        "meta_cognitivo": 1 if problemas_sueno >= 4 or estres_alto else 0,
    }
    row.update(build_diet_quantities(rng, tipo_dieta, nivel_actividad, peso_kg))
    attach_diet_metadata(row, rng)
    attach_benchmark_status_features(row, rng)
    row["symptom_burden_score"] = round(sum(float(row[col]) for col in SYMPTOM_COLS) / len(SYMPTOM_COLS), 3)
    row["high_symptom_count"] = sum(1 for col in SYMPTOM_COLS if int(row[col]) >= 4)

    row["lab_vitamin_d_status"] = lab_status(
        rng,
        low_probability=0.34 if exposicion_solar == "baja" else 0.14,
        critical_probability=0.05 if exposicion_solar == "baja" else 0.015,
    )
    row["lab_b12_status"] = lab_status(
        rng,
        low_probability=0.32 if tipo_dieta in {"vegano", "vegetariano"} else 0.10,
        critical_probability=0.04 if tipo_dieta == "vegano" else 0.015,
    )
    row["lab_ferritin_status"] = lab_status(rng, low_probability=0.24 if sexo == "F" else 0.11)
    row["lab_hemoglobin_status"] = lab_status(rng, low_probability=0.12 if row["lab_ferritin_status"] in {"low", "critical_low"} else 0.06)
    row["lab_magnesium_status"] = lab_status(rng, low_probability=0.17 if row["calambres"] >= 4 else 0.08)
    row["lab_zinc_status"] = lab_status(rng, low_probability=0.18 if row["enfermedad_frecuente"] >= 4 else 0.08)
    row["lab_calcium_status"] = lab_status(rng, low_probability=0.12 if edad >= 50 else 0.06)
    row["lab_folate_status"] = lab_status(rng, low_probability=0.18 if dieta_deficiente else 0.07)

    metabolic_risk = bmi >= 30 or edad >= 50
    lipid_risk = bmi >= 30 or edad >= 45
    row["lab_glucose_status"] = high_lab_status(
        rng,
        high_probability=0.22 if metabolic_risk else 0.08,
        critical_probability=0.035 if metabolic_risk else 0.01,
    )
    row["lab_total_cholesterol_status"] = high_lab_status(
        rng,
        high_probability=0.26 if lipid_risk else 0.10,
        critical_probability=0.02 if lipid_risk else 0.01,
    )
    row["lab_ldl_status"] = high_lab_status(
        rng,
        high_probability=0.24 if lipid_risk else 0.09,
        critical_probability=0.02 if lipid_risk else 0.01,
    )
    row["lab_hdl_status"] = lab_status(rng, low_probability=0.22 if bmi >= 28 else 0.08)
    row["lab_triglycerides_status"] = high_lab_status(
        rng,
        high_probability=0.24 if bmi >= 28 else 0.09,
        critical_probability=0.02 if bmi >= 28 else 0.01,
    )
    row["lab_creatinine_status"] = high_lab_status(
        rng,
        high_probability=0.10 if edad >= 55 else 0.04,
        critical_probability=0.015,
    )
    row["lab_egfr_status"] = lab_status(
        rng,
        low_probability=0.18 if row["lab_creatinine_status"] in {"high", "critical_high"} or edad >= 60 else 0.05,
        critical_probability=0.02 if edad >= 60 else 0.01,
    )
    liver_risk = bmi >= 30 or row["lab_glucose_status"] in {"high", "critical_high"}
    row["lab_alt_status"] = high_lab_status(
        rng,
        high_probability=0.13 if liver_risk else 0.05,
        critical_probability=0.015 if liver_risk else 0.005,
    )
    row["lab_ast_status"] = high_lab_status(
        rng,
        high_probability=0.12 if row["lab_alt_status"] in {"high", "critical_high"} else 0.05,
        critical_probability=0.015 if row["lab_alt_status"] in {"high", "critical_high"} else 0.005,
    )
    row["lab_tsh_status"] = thyroid_status(rng)
    attach_soft_signal_features(row)
    attach_lab_metadata(row, rng)
    return row


def rule_matches(row: dict[str, Any], rule: dict[str, Any]) -> bool:
    value = row.get(rule["field"])
    expected = rule.get("value")
    operator = rule["operator"]
    if operator == "eq":
        return value == expected
    if operator == "in":
        return value in set(expected)
    if operator == "contains":
        return isinstance(value, list) and expected in value
    if value is None:
        return False
    numeric_value = float(value)
    if numeric_value < 0:
        return False
    if operator == "gte":
        return numeric_value >= float(expected)
    if operator == "lte":
        return numeric_value <= float(expected)
    if operator == "lt":
        return numeric_value < float(expected)
    raise ValueError(f"Operador no soportado: {operator}")


def label_row(row: dict[str, Any], knowledge: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    labels = {}
    scores = {}
    evidence = {}
    for condition in knowledge["conditions"]["conditions"]:
        score = 0.04
        hits = []
        for rule in condition.get("rules", []):
            if rule_matches(row, rule):
                score += float(rule["weight"])
                hits.append(rule["field"])
        score += rng.uniform(-0.04, 0.04)
        score = max(0.0, min(0.98, score))
        code = condition["code"]
        scores[f"rule_score_{code}"] = round(score, 4)
        labels[f"target_{code}"] = 1 if score >= float(condition["positive_threshold"]) else 0
        evidence[f"evidence_{code}"] = "|".join(sorted(set(hits)))
    return {**labels, **scores, **evidence}


def generate_dataset(knowledge: dict[str, Any], n_rows: int, seed: int) -> pd.DataFrame:
    rng = random.Random(seed)
    rows = []
    for _ in range(n_rows):
        row = build_synthetic_row(rng)
        row.update(label_row(row, knowledge, rng))
        rows.append(row)
    return pd.DataFrame(rows)


def dataset_eda(df: pd.DataFrame, labels: list[str]) -> dict[str, Any]:
    target_cols = [f"target_{label}" for label in labels]
    return {
        "generated_at": utc_now(),
        "row_count": int(len(df)),
        "feature_count": int(len(CAT_COLS) + len(NUM_COLS)),
        "target_count": int(len(target_cols)),
        "label_prevalence": {
            label: round(float(df[f"target_{label}"].mean()), 4)
            for label in labels
        },
        "healthy_like_rows_without_targets": int((df[target_cols].sum(axis=1) == 0).sum()),
        "lab_status_distribution": {
            col: df[col].value_counts(dropna=False).to_dict()
            for col in CAT_COLS
            if col.startswith("lab_")
        },
        "numeric_summary": {
            col: {
                "mean": round(float(df[col].mean()), 4),
                "std": round(float(df[col].std()), 4),
                "min": round(float(df[col].min()), 4),
                "max": round(float(df[col].max()), 4),
            }
            for col in NUM_COLS
        },
    }


def source_audit_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    invalid_by_id = {item["id"]: item for item in report["invalid_domains"]}
    rows = []
    for source in report["sources"]:
        invalid = invalid_by_id.get(source["id"])
        rows.append(
            {
                "generated_at": report["generated_at"],
                "source_count": report["source_count"],
                "allowed_domains": "|".join(report["allowed_domains"]),
                "duplicate_ids": "|".join(report["duplicate_ids"]),
                "source_id": source["id"],
                "organization": source["organization"],
                "url": source["url"],
                "used_for": "|".join(source.get("used_for", [])),
                "invalid_domain": invalid["domain"] if invalid else "",
            }
        )
    return rows


def knowledge_eda_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for condition_code, rule_count in report["rules_by_condition"].items():
        rows.append(
            {
                "generated_at": report["generated_at"],
                "condition_count": report["condition_count"],
                "label_count": report["label_count"],
                "biomarker_count": report["biomarker_count"],
                "condition_component_link_count": report["condition_component_link_count"],
                "safety_rule_count": report["safety_rule_count"],
                "condition_code": condition_code,
                "rule_count": rule_count,
                "source_ids": "|".join(report["sources_by_condition"].get(condition_code, [])),
            }
        )
    return rows


def dataset_eda_to_csv(report: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    summary = [
        {
            "generated_at": report["generated_at"],
            "dataset_path": report.get("dataset_path", ""),
            "row_count": report["row_count"],
            "feature_count": report["feature_count"],
            "target_count": report["target_count"],
            "healthy_like_rows_without_targets": report["healthy_like_rows_without_targets"],
        }
    ]
    label_prevalence = [
        {"condition_code": label, "prevalence": prevalence}
        for label, prevalence in report["label_prevalence"].items()
    ]
    lab_distribution = []
    for lab_field, values in report["lab_status_distribution"].items():
        for status, count in values.items():
            lab_distribution.append({"lab_field": lab_field, "status": status, "count": count})
    numeric_summary = [
        {"feature": feature, **stats}
        for feature, stats in report["numeric_summary"].items()
    ]
    return {
        "summary": summary,
        "label_prevalence": label_prevalence,
        "lab_status_distribution": lab_distribution,
        "numeric_summary": numeric_summary,
    }


def feature_contract_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for col in CAT_COLS:
        if col in LAB_STATUS_COLS:
            group = "observed_labs"
            source = "ocr_or_manual_lab"
            missing = "missing category"
        elif col in BENCHMARK_STATUS_COLS:
            group = "real_benchmark_or_diet_status"
            source = "nhanes_or_survey_derived"
            missing = "missing category when unavailable"
        elif col == "lab_panel_source":
            group = "observed_labs"
            source = "ocr_or_manual_lab"
            missing = "none"
        else:
            group = "profile_or_survey"
            source = "self_reported"
            missing = "not generated in synthetic dataset"
        rows.append(
            {
                "feature": col,
                "dtype": "categorical",
                "group": group,
                "source": source,
                "missing_semantics": missing,
            }
        )

    symptom_set = set(SYMPTOM_COLS)
    diet_set = set(DIET_QUANTITY_COLS)
    diet_meta_set = set(DIET_META_COLS)
    soft_signal_set = set(SOFT_SIGNAL_COLS)
    lab_meta_set = set(LAB_META_COLS)
    for col in NUM_COLS:
        if col in symptom_set or col in {"symptom_burden_score", "high_symptom_count"}:
            group = "self_reported_symptoms"
            source = "self_reported"
            missing = "not zero; generated as ordinal burden"
        elif col in diet_set:
            group = "measurable_diet"
            source = "self_reported_quantity"
            missing = "-1 sentinel when not reported"
        elif col in diet_meta_set:
            group = "measurable_diet_metadata"
            source = "self_reported_quantity"
            missing = "reported=0 when quantity is missing"
        elif col in soft_signal_set:
            group = "derived_soft_signal"
            source = "survey_and_lab_derived"
            missing = "-1 only for unavailable numeric gaps; binary signals default to 0"
        elif col in lab_meta_set or col in {"observed_lab_count", "missing_lab_count"}:
            group = "observed_labs_metadata"
            source = "ocr_or_manual_lab"
            missing = "observed=0, age_days=999, known=0"
        elif col in {"edad", "peso_kg", "altura_cm", "bmi"}:
            group = "profile_anthropometrics"
            source = "profile"
            missing = "required or internally derived"
        else:
            group = "goals_or_context"
            source = "self_reported"
            missing = "binary false only when explicitly absent"
        rows.append(
            {
                "feature": col,
                "dtype": "numeric",
                "group": group,
                "source": source,
                "missing_semantics": missing,
            }
        )
    return rows


def safe_metric(fn, y_true: np.ndarray, y_pred_or_score: np.ndarray) -> float | None:
    try:
        value = fn(y_true, y_pred_or_score)
    except ValueError:
        return None
    if value is None or not math.isfinite(float(value)):
        return None
    return round(float(value), 4)


def optimize_prediction_thresholds(
    labels: list[str],
    y_true: np.ndarray,
    probabilities: np.ndarray,
    default_thresholds: dict[str, float],
) -> dict[str, float]:
    optimized: dict[str, float] = {}
    candidates = np.round(np.arange(0.20, 0.81, 0.01), 2)
    for index, label in enumerate(labels):
        best_threshold = float(default_thresholds[label])
        best_f1 = -1.0
        for threshold in candidates:
            y_pred = (probabilities[:, index] >= threshold).astype(int)
            value = f1_score(y_true[:, index], y_pred, zero_division=0)
            if value > best_f1 or (value == best_f1 and abs(float(threshold) - default_thresholds[label]) < abs(best_threshold - default_thresholds[label])):
                best_f1 = float(value)
                best_threshold = float(threshold)
        optimized[label] = round(best_threshold, 2)
    return optimized


def train_model(df: pd.DataFrame, knowledge: dict[str, Any], seed: int) -> dict[str, Any]:
    labels = knowledge["conditions"]["labels"]
    target_cols = [f"target_{label}" for label in labels]
    x = df[CAT_COLS + NUM_COLS]
    y = df[target_cols]

    x_train, x_test, y_train, y_test = train_test_split(
        x,
        y,
        test_size=0.22,
        random_state=seed,
    )

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), NUM_COLS),
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CAT_COLS),
        ]
    )
    base_estimator = CalibratedClassifierCV(
        estimator=LogisticRegression(
            class_weight="balanced",
            max_iter=1200,
            solver="liblinear",
            random_state=seed,
        ),
        method="sigmoid",
        cv=3,
    )
    pipeline = Pipeline(
        steps=[
            ("prep", preprocessor),
            ("clf", OneVsRestClassifier(base_estimator)),
        ]
    )
    pipeline.fit(x_train, y_train)

    probabilities = pipeline.predict_proba(x_test)
    y_true = y_test.to_numpy()
    label_thresholds = {
        condition["code"]: float(condition["positive_threshold"])
        for condition in knowledge["conditions"]["conditions"]
    }
    thresholds = optimize_prediction_thresholds(labels, y_true, probabilities, label_thresholds)
    threshold_array = np.array([thresholds[label] for label in labels])
    y_pred = (probabilities >= threshold_array).astype(int)

    per_label = {}
    for index, label in enumerate(labels):
        per_label[label] = {
            "label_threshold": label_thresholds[label],
            "prediction_threshold": thresholds[label],
            "prevalence_test": round(float(y_true[:, index].mean()), 4),
            "roc_auc": safe_metric(roc_auc_score, y_true[:, index], probabilities[:, index]),
            "pr_auc": safe_metric(average_precision_score, y_true[:, index], probabilities[:, index]),
            "brier": safe_metric(brier_score_loss, y_true[:, index], probabilities[:, index]),
            "precision": safe_metric(lambda a, b: precision_score(a, b, zero_division=0), y_true[:, index], y_pred[:, index]),
            "recall": safe_metric(lambda a, b: recall_score(a, b, zero_division=0), y_true[:, index], y_pred[:, index]),
            "f1": safe_metric(lambda a, b: f1_score(a, b, zero_division=0), y_true[:, index], y_pred[:, index]),
        }

    metrics = {
        "generated_at": utc_now(),
        "model_type": "OneVsRestClassifier(Calibrated LogisticRegression)",
        "disclaimer": "Modelo de probabilidades de riesgo/prioridad; no diagnostica.",
        "train_rows": int(len(x_train)),
        "test_rows": int(len(x_test)),
        "hamming_loss": round(float(hamming_loss(y_true, y_pred)), 4),
        "f1_macro": round(float(f1_score(y_true, y_pred, average="macro", zero_division=0)), 4),
        "f1_samples": round(float(f1_score(y_true, y_pred, average="samples", zero_division=0)), 4),
        "per_label": per_label,
    }

    artifact = {
        "pipeline": pipeline,
        "labels": labels,
        "cat_cols": CAT_COLS,
        "num_cols": NUM_COLS,
        "thresholds": thresholds,
        "label_thresholds": label_thresholds,
        "condition_rules": {
            condition["code"]: condition.get("rules", [])
            for condition in knowledge["conditions"]["conditions"]
        },
        "condition_requirements": {
            item["condition_code"]: item
            for item in knowledge["requirements"]["items"]
        },
        "source_version": knowledge["sources"]["version"],
        "conditions_version": knowledge["conditions"]["version"],
        "trained_at": utc_now(),
        "model_type": metrics["model_type"],
        "disclaimer": metrics["disclaimer"],
    }
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    model_path = RUNTIME_DIR / "condition_mvp_model.pkl"
    metadata_path = RUNTIME_DIR / "condition_mvp_metadata.csv"
    joblib.dump(artifact, model_path)
    write_csv(
        metadata_path,
        [
            {"key": "labels", "value": "|".join(labels)},
            {"key": "cat_cols", "value": "|".join(CAT_COLS)},
            {"key": "num_cols", "value": "|".join(NUM_COLS)},
            {"key": "thresholds", "value": "|".join(f"{key}:{value}" for key, value in thresholds.items())},
            {"key": "label_thresholds", "value": "|".join(f"{key}:{value}" for key, value in label_thresholds.items())},
            {"key": "feature_count", "value": str(len(CAT_COLS) + len(NUM_COLS))},
            {"key": "source_version", "value": artifact["source_version"]},
            {"key": "conditions_version", "value": artifact["conditions_version"]},
            {"key": "trained_at", "value": artifact["trained_at"]},
            {"key": "model_type", "value": artifact["model_type"]},
            {"key": "disclaimer", "value": artifact["disclaimer"]},
        ],
    )

    metrics["model_path"] = str(model_path.relative_to(ROOT_DIR))
    metrics["metadata_path"] = str(metadata_path.relative_to(ROOT_DIR))
    return metrics


def run_pipeline(args: argparse.Namespace) -> None:
    TRAINING_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    knowledge = load_knowledge()
    source_report = audit_sources(knowledge)
    knowledge_report = validate_knowledge(knowledge)
    write_csv(REPORT_DIR / "01_source_audit.csv", source_audit_rows(source_report))
    write_csv(REPORT_DIR / "02_knowledge_eda.csv", knowledge_eda_rows(knowledge_report))
    write_csv(TRAINING_DIR / "condition_feature_contract.csv", feature_contract_rows())

    df = generate_dataset(knowledge, n_rows=args.rows, seed=args.seed)
    dataset_path = TRAINING_DIR / "condition_training_dataset.csv"
    df.to_csv(dataset_path, index=False)
    eda_report = dataset_eda(df, knowledge["conditions"]["labels"])
    eda_report["dataset_path"] = str(dataset_path.relative_to(ROOT_DIR))
    eda_csv = dataset_eda_to_csv(eda_report)
    write_csv(REPORT_DIR / "03_dataset_eda_summary.csv", eda_csv["summary"])
    write_csv(REPORT_DIR / "03_dataset_label_prevalence.csv", eda_csv["label_prevalence"])
    write_csv(REPORT_DIR / "03_dataset_lab_status_distribution.csv", eda_csv["lab_status_distribution"])
    write_csv(REPORT_DIR / "03_dataset_numeric_summary.csv", eda_csv["numeric_summary"])

    metrics = train_model(df, knowledge, seed=args.seed)
    per_label = metrics.pop("per_label")
    write_csv(REPORT_DIR / "04_training_metrics.csv", [metrics])
    write_csv(
        REPORT_DIR / "04_training_metrics_by_label.csv",
        [{"condition_code": label, **values} for label, values in per_label.items()],
    )

    print("Pipeline condition_mvp completado")
    print(f"  fuentes: {REPORT_DIR / '01_source_audit.csv'}")
    print(f"  conocimiento/EDA: {REPORT_DIR / '02_knowledge_eda.csv'}")
    print(f"  dataset: {dataset_path}")
    print(f"  dataset EDA: {REPORT_DIR / '03_dataset_eda_summary.csv'}")
    print(f"  metricas: {REPORT_DIR / '04_training_metrics.csv'}")
    print(f"  modelo: {RUNTIME_DIR / 'condition_mvp_model.pkl'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Entrena modelo MVP de condiciones con base medica curada.")
    parser.add_argument("--rows", type=int, default=2500, help="Cantidad de filas semisinteticas a generar.")
    parser.add_argument("--seed", type=int, default=42, help="Semilla reproducible.")
    args = parser.parse_args()
    if args.rows < 500:
        raise SystemExit("--rows debe ser al menos 500 para que la calibracion por etiqueta sea estable.")
    run_pipeline(args)


if __name__ == "__main__":
    main()
