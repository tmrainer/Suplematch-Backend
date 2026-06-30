from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from app.core.config import settings


MODEL_FILENAME = "condition_mvp_model.pkl"

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
    "digestive_discomfort",
]

DIET_QUANTITY_COLS = [
    "fish_servings_week",
    "dairy_servings_day",
    "legume_servings_week",
    "meat_servings_week",
    "fruit_veg_servings_day",
    "protein_g_day_estimate",
    "fermented_foods_week",
    "water_intake_l_day",
]

SOFT_SIGNAL_COLS = [
    "vitamin_c_diet_signal",
    "protein_insufficient_signal",
    "protein_gap_g_day",
    "hair_skin_nails_cluster",
    "visual_strain_signal",
    "digestive_support_signal",
    "hydration_electrolyte_signal",
    "fatigue_nutrition_signal",
    "cardiovascular_context_signal",
    "cognitive_context_signal",
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

DIET_STATUS_COLS = [
    col
    for col in BENCHMARK_STATUS_COLS
    if col.startswith("benchmark_diet_")
]

LAB_BENCHMARK_STATUS_COLS = [
    col
    for col in BENCHMARK_STATUS_COLS
    if col.startswith("benchmark_lab_")
]

PROFILE_CONTEXT_COLS = {
    "sexo",
    "edad",
    "peso_kg",
    "altura_cm",
    "bmi",
}

SURVEY_CONTEXT_COLS = {
    "tipo_dieta",
    "exposicion_solar",
    "nivel_actividad",
    "dieta_deficiente",
    "estres_alto",
    "meta_energia",
    "meta_inmunidad",
    "meta_belleza",
    "meta_rendimiento",
    "meta_salud_osea",
    "meta_cognitivo",
    "meta_visual",
    "meta_digestiva",
    "meta_hidratacion",
    "meta_cardiovascular",
    "screen_hours_day",
    "heavy_sweat_days_week",
}

RUNTIME_CONTEXT_CONDITIONS: dict[str, dict[str, Any]] = {
    "SALUD_VISUAL": {
        "threshold": 0.55,
        "rules": [
            {"field": "meta_visual", "operator": "eq", "value": 1, "weight": 0.28},
            {"field": "screen_hours_day", "gte": 6, "operator": "gte", "value": 6, "weight": 0.22},
            {"field": "fruit_veg_servings_day", "operator": "lte", "value": 2, "weight": 0.12},
            {"field": "edad", "operator": "gte", "value": 50, "weight": 0.12},
            {"field": "visual_strain_signal", "operator": "eq", "value": 1, "weight": 0.24},
        ],
    },
    "SALUD_DIGESTIVA": {
        "threshold": 0.55,
        "rules": [
            {"field": "meta_digestiva", "operator": "eq", "value": 1, "weight": 0.30},
            {"field": "digestive_discomfort", "operator": "gte", "value": 3, "weight": 0.26},
            {"field": "fermented_foods_week", "operator": "lte", "value": 1, "weight": 0.12},
            {"field": "dieta_deficiente", "operator": "eq", "value": 1, "weight": 0.10},
            {"field": "digestive_support_signal", "operator": "eq", "value": 1, "weight": 0.22},
        ],
    },
    "FATIGA_NUTRICIONAL": {
        "threshold": 0.58,
        "rules": [
            {"field": "meta_energia", "operator": "eq", "value": 1, "weight": 0.18},
            {"field": "fatiga_general", "operator": "gte", "value": 4, "weight": 0.24},
            {"field": "benchmark_diet_b12_status", "operator": "in", "value": ["low", "critical_low"], "weight": 0.18},
            {"field": "benchmark_diet_protein_status", "operator": "in", "value": ["low", "critical_low"], "weight": 0.16},
            {"field": "dieta_deficiente", "operator": "eq", "value": 1, "weight": 0.10},
            {"field": "fatigue_nutrition_signal", "operator": "eq", "value": 1, "weight": 0.25},
        ],
    },
    "HIDRATACION_ELECTROLITOS": {
        "threshold": 0.55,
        "rules": [
            {"field": "meta_hidratacion", "operator": "eq", "value": 1, "weight": 0.26},
            {"field": "water_intake_l_day", "operator": "lte", "value": 1.2, "weight": 0.18},
            {"field": "heavy_sweat_days_week", "operator": "gte", "value": 3, "weight": 0.18},
            {"field": "calambres", "operator": "gte", "value": 3, "weight": 0.16},
            {"field": "hydration_electrolyte_signal", "operator": "eq", "value": 1, "weight": 0.24},
        ],
    },
    "SALUD_CARDIOVASCULAR_CONTEXTUAL": {
        "threshold": 0.58,
        "rules": [
            {"field": "meta_cardiovascular", "operator": "eq", "value": 1, "weight": 0.22},
            {"field": "edad", "operator": "gte", "value": 50, "weight": 0.14},
            {"field": "fish_servings_week", "operator": "lte", "value": 1, "weight": 0.14},
            {"field": "lab_total_cholesterol_status", "operator": "eq", "value": "high", "weight": 0.26},
            {"field": "lab_ldl_status", "operator": "eq", "value": "high", "weight": 0.26},
            {"field": "cardiovascular_context_signal", "operator": "eq", "value": 1, "weight": 0.22},
        ],
    },
    "SALUD_COGNITIVA": {
        "threshold": 0.55,
        "rules": [
            {"field": "meta_cognitivo", "operator": "eq", "value": 1, "weight": 0.22},
            {"field": "niebla_mental", "operator": "gte", "value": 3, "weight": 0.22},
            {"field": "problemas_sueno", "operator": "gte", "value": 4, "weight": 0.14},
            {"field": "benchmark_diet_omega3_status", "operator": "in", "value": ["low", "critical_low"], "weight": 0.12},
            {"field": "cognitive_context_signal", "operator": "eq", "value": 1, "weight": 0.24},
        ],
    },
}

MEDICAL_SAFETY_COLS = {
    "lab_creatinine_status",
    "lab_egfr_status",
    "lab_alt_status",
    "lab_ast_status",
    "lab_tsh_status",
    "lab_glucose_status",
    "lab_total_cholesterol_status",
    "lab_ldl_status",
    "lab_hdl_status",
    "lab_triglycerides_status",
}

SIGNAL_GROUP_ORDER = [
    "observed_lab",
    "medical_safety",
    "declared_diet",
    "self_reported_symptoms",
    "restrictions",
    "profile_context",
    "survey_context",
    "derived_soft_signal",
]


@lru_cache(maxsize=1)
def load_condition_mvp_model() -> dict[str, Any]:
    path = Path(settings.MODEL_DIR) / MODEL_FILENAME
    return joblib.load(path)


def _rule_matches(features: dict[str, Any], rule: dict[str, Any]) -> bool:
    value = features.get(rule["field"])
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
    return False


def _signal_group_for_field(field: str) -> str:
    if field in MEDICAL_SAFETY_COLS:
        return "medical_safety"
    if field in LAB_STATUS_COLS or field in LAB_BENCHMARK_STATUS_COLS:
        return "observed_lab"
    if field in DIET_QUANTITY_COLS or field in DIET_STATUS_COLS:
        return "declared_diet"
    if field in SYMPTOM_COLS:
        return "self_reported_symptoms"
    if field in {"condiciones_seguridad", "restricciones", "suplementos_actuales"}:
        return "restrictions"
    if field in PROFILE_CONTEXT_COLS:
        return "profile_context"
    if field in SOFT_SIGNAL_COLS:
        return "derived_soft_signal"
    if field in SURVEY_CONTEXT_COLS:
        return "survey_context"
    if field.endswith("_reported") or field.startswith("diet_"):
        return "declared_diet"
    if field.startswith("lab_"):
        return "observed_lab"
    return "survey_context"


def _signal_groups_from_rules(matched_rules: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for rule in matched_rules:
        field = str(rule["field"])
        group = _signal_group_for_field(field)
        bucket = grouped.setdefault(group, {"drivers": [], "weight": 0.0, "count": 0})
        if field not in bucket["drivers"]:
            bucket["drivers"].append(field)
        bucket["weight"] = round(float(bucket["weight"]) + float(rule.get("weight", 0.0)), 4)
        bucket["count"] = int(bucket["count"]) + 1

    for group, bucket in grouped.items():
        bucket["drivers"] = sorted(bucket["drivers"])
        if group in {"observed_lab", "medical_safety"}:
            bucket["strength"] = "alta"
        elif group in {"declared_diet", "self_reported_symptoms"}:
            bucket["strength"] = "media" if float(bucket["weight"]) >= 0.30 or int(bucket["count"]) >= 2 else "baja"
        else:
            bucket["strength"] = "baja"
    return grouped


def _primary_signal_group(signal_groups: dict[str, dict[str, Any]]) -> str:
    if not signal_groups:
        return "low_signal"
    for group in SIGNAL_GROUP_ORDER:
        if group in signal_groups:
            return group
    return sorted(signal_groups)[0]


def _evidence_level(primary_group: str, signal_groups: dict[str, dict[str, Any]], safety_flag: bool) -> str:
    if safety_flag and primary_group in {"medical_safety", "observed_lab"}:
        return "medical_safety"
    if primary_group == "observed_lab":
        return "observed_lab"
    if primary_group == "medical_safety":
        return "medical_safety"
    if primary_group == "declared_diet":
        return "declared_diet"
    if primary_group == "self_reported_symptoms":
        return "self_reported_symptoms"
    if primary_group == "restrictions":
        return "restrictions"
    if "declared_diet" in signal_groups and "self_reported_symptoms" in signal_groups:
        return "diet_and_symptoms"
    if signal_groups:
        return "self_reported"
    return "low_signal"


def _signal_strength(primary_group: str, signal_groups: dict[str, dict[str, Any]], rule_score: float) -> str:
    if primary_group in {"observed_lab", "medical_safety"}:
        return "alta"
    if primary_group in {"declared_diet", "self_reported_symptoms"}:
        return "media" if rule_score >= 0.45 or len(signal_groups) >= 2 else "baja"
    if rule_score >= 0.55:
        return "media"
    return "baja"


def _prepare_features(features: dict[str, Any], cat_cols: list[str], num_cols: list[str]) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "sexo": "F",
        "tipo_dieta": "omnivoro",
        "exposicion_solar": "media",
        "nivel_actividad": "moderado",
        "lab_panel_source": "none",
        "edad": 30,
        "peso_kg": 70.0,
        "altura_cm": 165.0,
        "bmi": 25.7,
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
        "fish_servings_week": -1.0,
        "dairy_servings_day": -1.0,
        "legume_servings_week": -1.0,
        "meat_servings_week": -1.0,
        "fruit_veg_servings_day": -1.0,
        "protein_g_day_estimate": -1.0,
        "fermented_foods_week": -1.0,
        "water_intake_l_day": -1.0,
        "screen_hours_day": -1.0,
        "heavy_sweat_days_week": -1,
        "digestive_discomfort": 1,
        "meta_visual": 0,
        "meta_digestiva": 0,
        "meta_hidratacion": 0,
        "meta_cardiovascular": 0,
    }
    for status_col in LAB_STATUS_COLS:
        defaults[status_col] = "missing"
    for status_col in BENCHMARK_STATUS_COLS:
        defaults[status_col] = "missing"

    row_payload = {**defaults, **features}
    diet_missing_count = 0
    for col in DIET_QUANTITY_COLS:
        reported = 1 if float(row_payload.get(col, -1)) >= 0 else 0
        diet_missing_count += 0 if reported else 1
        row_payload.setdefault(f"{col}_reported", reported)
    row_payload.setdefault("diet_quantity_missing_count", diet_missing_count)

    observed_lab_count = 0
    for status_col in LAB_STATUS_COLS:
        base = status_col.removeprefix("lab_").removesuffix("_status")
        observed = 0 if row_payload.get(status_col, "missing") == "missing" else 1
        observed_lab_count += observed
        row_payload.setdefault(f"lab_{base}_observed", observed)
        row_payload.setdefault(f"lab_{base}_age_days", 999 if not observed else 30)
        row_payload.setdefault(f"lab_{base}_unit_known", observed)
        row_payload.setdefault(f"lab_{base}_range_known", observed)

    row_payload.setdefault("observed_lab_count", observed_lab_count)
    row_payload.setdefault("missing_lab_count", len(LAB_STATUS_COLS) - observed_lab_count)
    row_payload.setdefault("symptom_burden_score", round(sum(float(row_payload[col]) for col in SYMPTOM_COLS) / len(SYMPTOM_COLS), 3))
    row_payload.setdefault("high_symptom_count", sum(1 for col in SYMPTOM_COLS if int(row_payload[col]) >= 4))
    _attach_soft_signal_features(row_payload)

    for col in cat_cols:
        row_payload.setdefault(col, "missing" if col.startswith("lab_") or col.startswith("benchmark_") else "unknown")
        if row_payload[col] is None:
            row_payload[col] = "missing" if col.startswith("lab_") or col.startswith("benchmark_") else "unknown"
        row_payload[col] = str(row_payload[col])
    for col in num_cols:
        row_payload.setdefault(col, 0)
        if row_payload[col] is None:
            row_payload[col] = 0
    return row_payload


def _attach_soft_signal_features(row_payload: dict[str, Any]) -> None:
    fruit_veg_reported = int(row_payload.get("fruit_veg_servings_day_reported", 0))
    fruit_veg = float(row_payload.get("fruit_veg_servings_day", -1))
    row_payload.setdefault(
        "vitamin_c_diet_signal",
        int(
            bool(fruit_veg_reported)
            and fruit_veg <= 2
            and (
                int(row_payload.get("dieta_deficiente", 0)) == 1
                or int(row_payload.get("enfermedad_frecuente", 0)) >= 4
                or int(row_payload.get("meta_inmunidad", 0)) == 1
            )
        ),
    )

    protein_reported = int(row_payload.get("protein_g_day_estimate_reported", 0))
    protein = float(row_payload.get("protein_g_day_estimate", -1))
    activity_multiplier = 1.2 if row_payload.get("nivel_actividad") in {"activo", "muy_activo"} else 0.85
    protein_target = float(row_payload.get("peso_kg", 70.0)) * activity_multiplier
    protein_gap = max(0.0, protein_target - protein) if protein_reported else -1.0
    row_payload.setdefault("protein_gap_g_day", round(protein_gap, 2))
    row_payload.setdefault(
        "protein_insufficient_signal",
        int(
            bool(protein_reported)
            and (
                protein < 55
                or protein_gap >= 20
                or (
                    row_payload.get("nivel_actividad") in {"activo", "muy_activo"}
                    and protein_gap >= 12
                    and int(row_payload.get("meta_rendimiento", 0)) == 1
                )
            )
        ),
    )

    hair_skin_hits = [
        int(row_payload.get("meta_belleza", 0)) == 1,
        int(row_payload.get("caida_cabello", 0)) >= 4,
        int(row_payload.get("piel_seca", 0)) >= 4,
        int(row_payload.get("unas_quebradizas", 0)) >= 4,
        row_payload.get("lab_zinc_status") in {"low", "critical_low"},
        row_payload.get("lab_ferritin_status") in {"low", "critical_low"},
    ]
    row_payload.setdefault("hair_skin_nails_cluster", sum(1 for hit in hair_skin_hits if hit))

    screen_reported = float(row_payload.get("screen_hours_day", -1)) >= 0
    screen_hours = float(row_payload.get("screen_hours_day", -1))
    row_payload.setdefault(
        "visual_strain_signal",
        int(
            (
                int(row_payload.get("meta_visual", 0)) == 1
                or (screen_reported and screen_hours >= 6)
            )
            and (
                fruit_veg <= 2 if fruit_veg_reported else True
            )
        ),
    )

    fermented_reported = float(row_payload.get("fermented_foods_week", -1)) >= 0
    fermented_foods = float(row_payload.get("fermented_foods_week", -1))
    digestive_discomfort = int(row_payload.get("digestive_discomfort", 1))
    row_payload.setdefault(
        "digestive_support_signal",
        int(
            int(row_payload.get("meta_digestiva", 0)) == 1
            or digestive_discomfort >= 3
            or (fermented_reported and fermented_foods <= 1 and int(row_payload.get("dieta_deficiente", 0)) == 1)
        ),
    )

    water_reported = float(row_payload.get("water_intake_l_day", -1)) >= 0
    water_l_day = float(row_payload.get("water_intake_l_day", -1))
    heavy_sweat_days = int(row_payload.get("heavy_sweat_days_week", -1))
    row_payload.setdefault(
        "hydration_electrolyte_signal",
        int(
            int(row_payload.get("meta_hidratacion", 0)) == 1
            or (water_reported and water_l_day <= 1.2)
            or heavy_sweat_days >= 3
            or int(row_payload.get("calambres", 1)) >= 3
        ),
    )

    row_payload.setdefault(
        "fatigue_nutrition_signal",
        int(
            int(row_payload.get("fatiga_general", 1)) >= 4
            and (
                int(row_payload.get("dieta_deficiente", 0)) == 1
                or row_payload.get("benchmark_diet_b12_status") in {"low", "critical_low"}
                or row_payload.get("benchmark_diet_protein_status") in {"low", "critical_low"}
            )
        ),
    )

    row_payload.setdefault(
        "cardiovascular_context_signal",
        int(
            int(row_payload.get("meta_cardiovascular", 0)) == 1
            or row_payload.get("lab_total_cholesterol_status") == "high"
            or row_payload.get("lab_ldl_status") == "high"
            or (
                int(row_payload.get("edad", 30)) >= 50
                and float(row_payload.get("fish_servings_week", -1)) >= 0
                and float(row_payload.get("fish_servings_week", -1)) <= 1
            )
        ),
    )

    row_payload.setdefault(
        "cognitive_context_signal",
        int(
            int(row_payload.get("meta_cognitivo", 0)) == 1
            or int(row_payload.get("niebla_mental", 1)) >= 3
            or (
                int(row_payload.get("problemas_sueno", 1)) >= 4
                and int(row_payload.get("fatiga_general", 1)) >= 3
            )
        ),
    )


def _runtime_context_predictions(row_payload: dict[str, Any]) -> list[dict[str, Any]]:
    predictions: list[dict[str, Any]] = []
    for label, config in RUNTIME_CONTEXT_CONDITIONS.items():
        threshold = float(config["threshold"])
        rules = config["rules"]
        matched_rule_details = [
            {
                "field": rule["field"],
                "operator": rule["operator"],
                "value": rule.get("value"),
                "weight": float(rule.get("weight", 0.0)),
                "signal_group": _signal_group_for_field(str(rule["field"])),
            }
            for rule in rules
            if _rule_matches(row_payload, rule)
        ]
        rule_score = round(sum(float(rule["weight"]) for rule in matched_rule_details), 4)
        probability = round(min(0.92, rule_score), 4)
        signal_groups = _signal_groups_from_rules(matched_rule_details)
        primary_signal_group = _primary_signal_group(signal_groups)
        evidence_level = _evidence_level(primary_signal_group, signal_groups, False)
        predictions.append(
            {
                "condition": label,
                "probability": probability,
                "model_probability": 0.0,
                "threshold": threshold,
                "positive": bool(probability >= threshold),
                "drivers": sorted({rule["field"] for rule in matched_rule_details}),
                "driver_details": matched_rule_details,
                "missing_data": [],
                "evidence_level": evidence_level,
                "primary_signal_group": primary_signal_group,
                "signal_strength": _signal_strength(primary_signal_group, signal_groups, rule_score),
                "signal_groups": signal_groups,
                "rule_score": rule_score,
                "calibrated_by_rules": True,
                "safety_flag": False,
                "runtime_contextual": True,
            }
        )
    return predictions


def predict_condition_probabilities(features: dict[str, Any]) -> list[dict[str, Any]]:
    artifact = load_condition_mvp_model()
    labels: list[str] = artifact["labels"]
    cat_cols: list[str] = artifact["cat_cols"]
    num_cols: list[str] = artifact["num_cols"]
    thresholds: dict[str, float] = artifact["thresholds"]
    pipeline = artifact["pipeline"]
    condition_rules: dict[str, list[dict[str, Any]]] = artifact.get("condition_rules", {})
    condition_requirements: dict[str, dict[str, Any]] = artifact.get("condition_requirements", {})

    row_payload = _prepare_features(features, cat_cols, num_cols)
    row = pd.DataFrame([row_payload])[cat_cols + num_cols]
    probabilities = pipeline.predict_proba(row)[0]

    response = []
    for label, probability in zip(labels, probabilities):
        threshold = float(thresholds[label])
        matched_rule_details = [
            {
                "field": rule["field"],
                "operator": rule["operator"],
                "value": rule.get("value"),
                "weight": float(rule.get("weight", 0.0)),
                "signal_group": _signal_group_for_field(str(rule["field"])),
            }
            for rule in condition_rules.get(label, [])
            if _rule_matches(row_payload, rule)
        ]
        matched_rules = [rule["field"] for rule in matched_rule_details]
        rule_score = round(sum(float(rule["weight"]) for rule in matched_rule_details), 4)
        model_probability = float(probability)
        calibrated_by_rules = False
        final_probability = model_probability
        if rule_score >= threshold and model_probability < threshold:
            final_probability = min(0.98, threshold + min(0.12, max(0.03, rule_score - threshold)))
            calibrated_by_rules = True
        requirement = condition_requirements.get(label, {})
        missing_data = [
            item
            for item in requirement.get("needs_lab_fields", [])
            if row_payload.get(f"lab_{item}_status") == "missing"
        ]
        signal_groups = _signal_groups_from_rules(matched_rule_details)
        primary_signal_group = _primary_signal_group(signal_groups)
        evidence_level = _evidence_level(primary_signal_group, signal_groups, label.startswith("SAFETY_"))
        signal_strength = _signal_strength(primary_signal_group, signal_groups, rule_score)
        response.append(
            {
                "condition": label,
                "probability": round(float(final_probability), 4),
                "model_probability": round(model_probability, 4),
                "threshold": threshold,
                "positive": bool(float(final_probability) >= threshold),
                "drivers": sorted(set(matched_rules)),
                "driver_details": matched_rule_details,
                "missing_data": sorted(set(missing_data)),
                "evidence_level": evidence_level,
                "primary_signal_group": primary_signal_group,
                "signal_strength": signal_strength,
                "signal_groups": signal_groups,
                "rule_score": rule_score,
                "calibrated_by_rules": calibrated_by_rules,
                "safety_flag": label.startswith("SAFETY_"),
            }
        )

    response.extend(_runtime_context_predictions(row_payload))
    response.sort(key=lambda item: item["probability"], reverse=True)
    return response
