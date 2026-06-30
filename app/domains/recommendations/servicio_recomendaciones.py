from __future__ import annotations

import math
from uuid import uuid4
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from app.domains.survey.esquemas_encuesta import EncuestaInput
from app.db.models import User
from app.ml.feature_builder import FeatureBuilder
from app.core.errors import ModelNotLoadedError, RecommendationGenerationError
from app.core.observability import log_event, metrics
from app.domains.recommendations.repositorio_metricas_recomendacion import RecommendationMetricsRepository
from app.domains.recommendations.repositorio_recomendaciones import RecommendationRepository
from app.domains.users.repositorio_usuarios import UserRepository
from app.domains.labs.servicio_analisis_examenes import LabAnalysisService
from app.domains.catalog.servicio_catalogo_productos import ProductCatalogService
from app.domains.recommendations.reglas_presentacion import (
    BIOMEDICAL_RISK_CONDITIONS,
    COMPONENT_DOSAGE_HINTS,
    COMPONENT_ICONS,
    CONDITION_ALIASES,
    CONDITION_LABELS,
    CURRENT_SUPPLEMENT_KEYWORDS,
    DISCLAIMER,
    HARD_SAFETY_CONDITIONS,
    NUTRITION_RISK_CONDITIONS,
    RESTRICTION_WARNING_LABELS,
    SAFETY_FLAG_CONDITIONS,
    SECURITY_WARNING_LABELS,
    TYPE_LABELS,
    WELLNESS_PRIORITY_CONDITIONS,
    _translate_component_name,
)


def _to_builtin(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _to_builtin(v) for k, v in value.items()}

    if isinstance(value, list):
        return [_to_builtin(v) for v in value]

    if isinstance(value, tuple):
        return [_to_builtin(v) for v in value]

    if isinstance(value, np.integer):
        return int(value)

    if isinstance(value, np.floating):
        return float(value)

    if isinstance(value, np.bool_):
        return bool(value)

    if isinstance(value, np.ndarray):
        return value.tolist()

    return value


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value

    return None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def _clean_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(number):
        return None

    return number


def _clean_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _humanize_code(value: str | None) -> str:
    if value is None:
        return "Perfil evaluado"

    return (
        value.replace("_", " ")
        .strip()
        .lower()
        .capitalize()
    )


def _condition_display_name(condition: str | None) -> str:
    if condition is None:
        return "Perfil evaluado"

    return CONDITION_LABELS.get(condition, _humanize_code(condition))


def _type_display_name(value: str | None) -> str | None:
    if value is None:
        return None

    return TYPE_LABELS.get(value, _humanize_code(value))


def _component_icon_key(name: str) -> str:
    clean = name.lower()

    for key, icon in COMPONENT_ICONS.items():
        if key in clean:
            return icon

    return "pill"


def _dosage_hint(name: str, rec_type: str | None) -> str:
    clean = name.lower()

    for key, hint in COMPONENT_DOSAGE_HINTS.items():
        if key in clean:
            return hint

    if rec_type == "semilla_directa":
        return "Prioritario para el perfil detectado"

    return "Complementario para el perfil detectado"


def _current_supplement_match(name: str | None, current_supplements: list[str]) -> bool:
    clean = (name or "").lower()
    for supplement in current_supplements:
        if any(keyword in clean for keyword in CURRENT_SUPPLEMENT_KEYWORDS.get(supplement, ())):
            return True
    return False


CURRENT_SUPPLEMENT_DOSE_THRESHOLDS: dict[str, dict[str, float]] = {
    "vitamina_d": {"low_below": 600.0, "high_at": 4000.0},
    "calcio": {"low_below": 300.0, "high_at": 1200.0},
    "magnesio": {"low_below": 100.0, "high_at": 350.0},
    "zinc": {"low_below": 8.0, "high_at": 40.0},
    "vitamina_c": {"low_below": 200.0, "high_at": 1000.0},
    "hierro": {"low_below": 14.0, "high_at": 45.0},
    "omega_3": {"low_below": 250.0, "high_at": 2000.0},
    "proteina": {"low_below": 20.0, "high_at": 120.0},
}


def _matched_current_supplement(name: str | None, current_supplements: list[str]) -> str | None:
    clean = (name or "").lower()
    for supplement in current_supplements:
        if any(keyword in clean for keyword in CURRENT_SUPPLEMENT_KEYWORDS.get(supplement, ())):
            return supplement
    return None


def _current_dose_amount_in_reference_unit(supplement: str, dose: Any) -> float | None:
    amount = _clean_float(getattr(dose, "amount", None) if not isinstance(dose, dict) else dose.get("amount"))
    if amount is None or amount <= 0:
        return None

    unit = str(getattr(dose, "unit", None) if not isinstance(dose, dict) else dose.get("unit") or "").lower()
    if supplement == "vitamina_d" and ("mcg" in unit or "µg" in unit):
        return amount * 40.0

    return amount


def _current_supplement_dose_context(
    supplement: str | None,
    encuesta: EncuestaInput,
) -> dict[str, Any] | None:
    if not supplement:
        return None

    doses = getattr(encuesta, "suplementos_dosis_actual", {}) or {}
    dose = doses.get(supplement) if isinstance(doses, dict) else None
    if not dose:
        return {"supplement": supplement, "status": "unknown"}

    amount = _clean_float(getattr(dose, "amount", None) if not isinstance(dose, dict) else dose.get("amount"))
    unit = str(getattr(dose, "unit", None) if not isinstance(dose, dict) else dose.get("unit") or "")
    comparable = _current_dose_amount_in_reference_unit(supplement, dose)
    thresholds = CURRENT_SUPPLEMENT_DOSE_THRESHOLDS.get(supplement)
    if comparable is None or not thresholds:
        return {"supplement": supplement, "amount": amount, "unit": unit, "status": "unknown"}

    if comparable >= thresholds["high_at"]:
        status = "high"
    elif comparable < thresholds["low_below"]:
        status = "low"
    else:
        status = "covered"

    return {
        "supplement": supplement,
        "amount": amount,
        "unit": unit,
        "status": status,
        "reference_low_below": thresholds["low_below"],
        "reference_high_at": thresholds["high_at"],
    }


def _should_block_current_supplement_purchase(dose_context: dict[str, Any] | None) -> bool:
    if not dose_context:
        return False
    return dose_context.get("status") in {"unknown", "covered", "high"}


def _product_current_supplement_match(product: dict[str, Any], current_supplements: list[str]) -> bool:
    text = " ".join(
        str(product.get(key) or "")
        for key in (
            "commercial_name",
            "formal_name",
            "ingredient",
            "component_name",
            "component_display_name",
        )
    )
    return _current_supplement_match(text, current_supplements)


def _profile_warnings(encuesta: EncuestaInput) -> list[str]:
    warnings = []
    current_supplements = getattr(encuesta, "suplementos_actuales", []) or []
    if current_supplements:
        warnings.append("Ya consumes suplementos: evita duplicar dosis sin revisar etiqueta y dosis total diaria.")

    for item in getattr(encuesta, "condiciones_seguridad", []) or []:
        warning = SECURITY_WARNING_LABELS.get(item)
        if warning and warning not in warnings:
            warnings.append(warning)

    for item in getattr(encuesta, "restricciones", []) or []:
        warning = RESTRICTION_WARNING_LABELS.get(item)
        if warning and warning not in warnings:
            warnings.append(warning)

    if getattr(encuesta, "edad_rango", None) == "menos_18":
        warnings.append("Menor de edad: las recomendaciones requieren supervisión de un adulto y profesional de salud.")

    return warnings


def _safety_level(encuesta: EncuestaInput) -> str:
    if getattr(encuesta, "edad_rango", None) == "menos_18":
        return "medical_review_required"

    conditions = set(getattr(encuesta, "condiciones_seguridad", []) or [])
    if conditions.intersection(HARD_SAFETY_CONDITIONS):
        return "medical_review_required"

    if (
        conditions
        or getattr(encuesta, "restricciones", None)
        or getattr(encuesta, "suplementos_actuales", None)
    ):
        return "caution"

    return "normal"


def _safety_actions(encuesta: EncuestaInput) -> list[str]:
    level = _safety_level(encuesta)
    if level == "normal":
        return []

    actions = [
        "No iniciar ni combinar suplementos solo con esta recomendación.",
        "Revisar etiqueta, dosis total diaria y posibles interacciones.",
    ]

    if level == "medical_review_required":
        actions.insert(0, "Validar el plan con un profesional de salud antes de comprar o consumir.")

    return actions


def _lab_analysis_for_survey(encuesta: EncuestaInput) -> dict[str, Any] | None:
    lab_results = getattr(encuesta, "lab_results", []) or []
    if not lab_results:
        return None
    return LabAnalysisService().analyze_manual(lab_results, persist=False, source_note="survey_lab_results")


def _combine_safety_level(survey_level: str, lab_analysis: dict[str, Any] | None) -> str:
    if lab_analysis and lab_analysis.get("safety_level") == "medical_review_required":
        return "medical_review_required"
    if survey_level == "medical_review_required":
        return survey_level
    if lab_analysis and lab_analysis.get("safety_level") == "caution":
        return "caution"
    return survey_level


def _merge_lab_supplement_signals(
    recommendations: list[dict[str, Any]],
    lab_analysis: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not lab_analysis:
        return recommendations

    existing_names = {
        str(item.get("name") or item.get("display_name") or "").strip().lower()
        for item in recommendations
    }
    merged = list(recommendations)
    for signal in lab_analysis.get("supplement_signals", []):
        supplement = str(signal.get("supplement") or "").strip()
        if not supplement or supplement.lower() in existing_names:
            continue
        component_id = str(signal.get("component_id") or f"lab_{signal.get('biomarker_code') or supplement.lower()}")
        merged.append(
            {
                "component_id": component_id,
                "name": supplement,
                "display_name": _translate_component_name(supplement),
                "condition": "LAB_RESULT",
                "condition_display": "Resultado de laboratorio",
                "score": 0.88,
                "type": "lab_signal",
                "type_display": "Señal por examen",
                "reason": signal.get("reason") or "Señal detectada en examen cargado.",
                "dosage_hint": "Validar dosis y necesidad con profesional de salud.",
                "priority": "lab_signal",
                "icon_key": _component_icon_key(supplement),
                "products": [],
                "already_taking": False,
                "safety_note": "Basado en examen cargado; no es diagnóstico.",
            }
        )
    return merged


def _survey_profile_values(encuesta: EncuestaInput) -> dict[str, Any]:
    return {
        "sex": getattr(encuesta, "sexo", None),
        "diet_type": getattr(encuesta, "tipo_dieta", None),
        "activity_level": getattr(encuesta, "frecuencia_ejercicio", None),
        "age_years": getattr(encuesta, "age_years", None),
        "weight_value": getattr(encuesta, "weight_value", None),
        "weight_unit": getattr(encuesta, "weight_unit", None),
        "weight_kg": getattr(encuesta, "weight_kg", None),
        "height_value": getattr(encuesta, "height_value", None),
        "height_unit": getattr(encuesta, "height_unit", None),
        "height_cm": getattr(encuesta, "height_cm", None),
        "health_goals": {
            "objetivo_principal": getattr(encuesta, "objetivo_principal", None),
            "objetivos": getattr(encuesta, "objetivos", []) or [],
            "presupuesto": getattr(encuesta, "presupuesto", None),
            "presupuesto_min": getattr(encuesta, "presupuesto_min", None),
            "presupuesto_max": getattr(encuesta, "presupuesto_max", None),
            "preferred_pack_size": getattr(encuesta, "preferred_pack_size", 3),
            "toma_suplementos": getattr(encuesta, "toma_suplementos", "no"),
            "suplementos_actuales": getattr(encuesta, "suplementos_actuales", []) or [],
            "suplementos_frecuencia": getattr(encuesta, "suplementos_frecuencia", None),
            "suplementos_dosis_conocida": getattr(encuesta, "suplementos_dosis_conocida", None),
            "edad_rango": getattr(encuesta, "edad_rango", None),
            "peso_rango": getattr(encuesta, "peso_rango", None),
            "talla_rango": getattr(encuesta, "talla_rango", None),
            "height_value": getattr(encuesta, "height_value", None),
            "height_unit": getattr(encuesta, "height_unit", None),
            "height_cm": getattr(encuesta, "height_cm", None),
            "bmi": getattr(encuesta, "bmi", None),
        },
        "diet_metrics": {
            "fish_servings_week": getattr(encuesta, "fish_servings_week", None),
            "dairy_servings_day": getattr(encuesta, "dairy_servings_day", None),
            "dairy_servings_week": getattr(encuesta, "dairy_servings_week", None),
            "legume_servings_week": getattr(encuesta, "legume_servings_week", None),
            "meat_servings_week": getattr(encuesta, "meat_servings_week", None),
            "red_meat_servings_week": getattr(encuesta, "red_meat_servings_week", None),
            "poultry_servings_week": getattr(encuesta, "poultry_servings_week", None),
            "eggs_servings_week": getattr(encuesta, "eggs_servings_week", None),
            "no_meat": getattr(encuesta, "no_meat", None),
            "fruit_veg_servings_day": getattr(encuesta, "fruit_veg_servings_day", None),
            "protein_g_day_estimate": getattr(encuesta, "protein_g_day_estimate", None),
            "iron_anemia_history": getattr(encuesta, "iron_anemia_history", None),
            "water_intake_l_day": getattr(encuesta, "water_intake_l_day", None),
            "heavy_sweat_days_week": getattr(encuesta, "heavy_sweat_days_week", None),
            "headache_days_week": getattr(encuesta, "headache_days_week", None),
            "fatigue_days_week": getattr(encuesta, "fatigue_days_week", None),
            "alcohol_drinks_week": getattr(encuesta, "alcohol_drinks_week", None),
        },
        "sleep_metrics": {
            "sleep_quality": getattr(encuesta, "sleep_quality", None),
            "night_wakeups": getattr(encuesta, "night_wakeups", None),
            "caffeine_after_3pm": getattr(encuesta, "caffeine_after_3pm", None),
            "caffeine_sources": getattr(encuesta, "caffeine_sources", []) or [],
            "caffeine_servings_day": getattr(encuesta, "caffeine_servings_day", None),
        },
        "activity_metrics": {
            "exercise_days_week": getattr(encuesta, "exercise_days_week", None),
            "training_type": getattr(encuesta, "training_type", None),
            "recovery_difficulty": getattr(encuesta, "recovery_difficulty", None),
        },
        "allergies": {
            "restricciones": getattr(encuesta, "restricciones", []) or [],
        },
        "medical_warnings": {
            "condiciones_seguridad": getattr(encuesta, "condiciones_seguridad", []) or [],
        },
    }


def _annotate_current_supplements(recommendations: list[dict[str, Any]], encuesta: EncuestaInput) -> list[dict[str, Any]]:
    current_supplements = getattr(encuesta, "suplementos_actuales", []) or []
    if not current_supplements:
        return recommendations

    for recommendation in recommendations:
        already_taking = _current_supplement_match(
            recommendation.get("name") or recommendation.get("display_name"),
            current_supplements,
        )
        recommendation["already_taking"] = already_taking
        if already_taking:
            recommendation["safety_note"] = "Indicas que ya consumes algo similar; revisar dosis y evitar duplicar."
            recommendation["products"] = []
            recommendation["commercial_eligible"] = False
            recommendation["commercial_recommendation_blocked"] = True
            recommendation["commercial_block_reason"] = (
                "Ya declaraste que consumes algo similar; no mostramos compra directa para evitar duplicar dosis."
            )
    return recommendations


def _filter_pack_products_for_current_supplements(
    packs_ranked: list[dict[str, Any]],
    encuesta: EncuestaInput,
) -> list[dict[str, Any]]:
    current_supplements = getattr(encuesta, "suplementos_actuales", []) or []
    if not current_supplements:
        return packs_ranked

    filtered_packs: list[dict[str, Any]] = []
    for pack in packs_ranked:
        selected_products = [
            product
            for product in pack.get("selected_products", [])
            if not _product_current_supplement_match(product, current_supplements)
        ]
        filtered_packs.append(
            {
                **pack,
                "selected_products": selected_products,
                "score_products": pack.get("score_products") if selected_products else None,
            }
        )
    return filtered_packs


def _recommendation_reason(condition: str | None, rec_type: str | None) -> str:
    if condition and condition != "soporte_funcional":
        return f"Relacionado con {_condition_display_name(condition).lower()}."

    if rec_type == "candidato_gnn":
        return "Complementa el pack por soporte funcional."

    return "Recomendado para el perfil evaluado."


def _condition_probability_fallback(index: int, total: int) -> float:
    if total <= 1:
        return 0.82
    return max(0.45, 0.82 - (index * 0.12))


def _condition_level(probability: float) -> str:
    if probability >= 0.70:
        return "Alta prioridad"
    if probability >= 0.55:
        return "Prioridad media"
    return "Contexto"


def _canonical_condition(condition: str) -> str:
    return CONDITION_ALIASES.get(condition, condition)


def _condition_kind(condition: str) -> str:
    if condition in SAFETY_FLAG_CONDITIONS:
        return "safety_flag"
    if condition in NUTRITION_RISK_CONDITIONS:
        return "nutrition_risk"
    if condition in BIOMEDICAL_RISK_CONDITIONS:
        return "biomedical_risk"
    if condition in WELLNESS_PRIORITY_CONDITIONS:
        return "wellness_priority"
    return "context"


def _condition_evidence_group(condition: str) -> str:
    if condition in SAFETY_FLAG_CONDITIONS:
        return "safety_only"
    if condition in {"RIESGO_METABOLICO_GLUCOSA", "RIESGO_DISLIPIDEMIA"}:
        return "lab_only"
    if condition in {
        "DEFICIT_B12",
        "DEFICIT_CALCIO",
        "DEFICIT_FOLATO",
        "DEFICIT_MAGNESIO",
        "DEFICIT_ZINC",
        "RIESGO_VITAMINA_C_BAJA",
        "RIESGO_OMEGA3_BAJO",
        "RIESGO_PROTEINA_INSUFICIENTE",
    }:
        return "diet_or_lab"
    if condition in {"DEFICIT_VIT_D", "DEFICIT_HIERRO", "RIESGO_SALUD_OSEA", "SALUD_OSEA"}:
        return "lab_or_diet"
    if condition in WELLNESS_PRIORITY_CONDITIONS:
        return "survey_wellness"
    return "unknown"


def _condition_benchmark_status(condition: str) -> str:
    if condition in WELLNESS_PRIORITY_CONDITIONS:
        return "not_evaluable_with_nhanes_use_survey_golden_cases"
    if condition in {"BAJA_INMUNIDAD"}:
        return "not_evaluable_with_nhanes"
    if condition in NUTRITION_RISK_CONDITIONS or condition in BIOMEDICAL_RISK_CONDITIONS or condition in SAFETY_FLAG_CONDITIONS:
        return "evaluated_with_nhanes_when_data_available"
    return "not_evaluated"


def _condition_validation_source(condition: str) -> str:
    if condition in WELLNESS_PRIORITY_CONDITIONS:
        return "survey_rules_and_future_golden_cases"
    if condition in NUTRITION_RISK_CONDITIONS:
        return "nhanes_multi_cycle_diet_lab_rules"
    if condition in BIOMEDICAL_RISK_CONDITIONS or condition in SAFETY_FLAG_CONDITIONS:
        return "nhanes_multi_cycle_lab_rules"
    return "internal_rules"


def _confidence_label(probability: float, kind: str, evidence_group: str) -> str:
    if kind == "wellness_priority":
        if probability >= 0.80:
            return "media"
        return "baja"
    if evidence_group in {"lab_only", "lab_or_diet", "diet_or_lab", "safety_only"} and probability >= 0.70:
        return "alta"
    if probability >= 0.55:
        return "media"
    return "baja"


def _recommendation_strength(probability: float, kind: str) -> str:
    if kind == "safety_flag":
        return "bloqueada"
    if kind == "context":
        return "no_convertir"
    if kind == "wellness_priority":
        return "no_convertir"
    if probability >= 0.75:
        return "alta"
    if probability >= 0.55:
        return "media"
    return "baja"


def _condition_result_explanation(condition: str, kind: str) -> str:
    if kind == "safety_flag":
        return "Alerta de seguridad: requiere revisión profesional antes de convertir esto en productos comerciales."
    if kind == "wellness_priority":
        return "Prioridad de bienestar estimada por encuesta; no es diagnóstico y no genera compra directa sin evidencia nutricional adicional."
    if kind in {"nutrition_risk", "biomedical_risk"}:
        return "Riesgo estimado por señales estructuradas de encuesta, dieta o laboratorio cuando están disponibles."
    return "Señal contextual usada para ordenar recomendaciones, no como condición clínica."


def _categorized_condition_results(
    conditions: list[str],
    condition_scores: dict[str, float] | None = None,
    condition_details: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    scores = condition_scores or {}
    details_by_condition = {
        _canonical_condition(str(item.get("condition"))): item
        for item in condition_details or []
        if item.get("condition")
    }
    total = len(conditions)
    results: list[dict[str, Any]] = []
    seen = set()

    for index, raw_condition in enumerate(conditions):
        condition = _canonical_condition(raw_condition)
        if condition in seen:
            continue
        seen.add(condition)

        probability = scores.get(raw_condition, scores.get(condition, _condition_probability_fallback(index, total)))
        probability = float(probability)
        detail = details_by_condition.get(condition, {})
        kind = _condition_kind(condition)
        evidence_group = str(detail.get("evidence_level") or _condition_evidence_group(condition))
        result = {
            "code": condition,
            "display_name": _condition_display_name(condition),
            "kind": kind,
            "probability": probability,
            "level": _condition_level(probability),
            "evidence_group": evidence_group,
            "confidence_label": _confidence_label(probability, kind, evidence_group),
            "recommendation_strength": _recommendation_strength(probability, kind),
            "benchmark_status": _condition_benchmark_status(condition),
            "validation_source": _condition_validation_source(condition),
            "primary_signal_group": str(detail.get("primary_signal_group") or "unknown"),
            "signal_strength": str(detail.get("signal_strength") or "baja"),
            "signal_groups": detail.get("signal_groups") or {},
            "drivers": detail.get("drivers") or [],
            "missing_data": detail.get("missing_data") or [],
            "model_probability": detail.get("model_probability"),
            "rule_score": detail.get("rule_score"),
            "calibrated_by_rules": bool(detail.get("calibrated_by_rules")),
            "allowed_for_commercial_recommendation": kind not in {"safety_flag", "wellness_priority"},
            "requires_disclaimer": True,
            "explanation": _condition_result_explanation(condition, kind),
        }
        results.append(result)

    condition_results = [
        result
        for result in results
        if result["kind"] in {"nutrition_risk", "biomedical_risk", "context"}
    ]
    wellness_priorities = [
        result
        for result in results
        if result["kind"] == "wellness_priority"
    ]
    safety_flags = [
        result
        for result in results
        if result["kind"] == "safety_flag"
    ]

    return condition_results, wellness_priorities, safety_flags


def _recommendation_reason_with_score(
    condition: str | None,
    condition_score: float | None,
    rec_type: str | None,
) -> str:
    if condition and condition != "soporte_funcional":
        name = _condition_display_name(condition).lower()
        if condition_score and condition_score >= 0.70:
            return f"Alta prioridad por {name} (confianza {round(condition_score * 100)}%)."
        if condition_score and condition_score >= 0.50:
            return f"Indicado para {name} (confianza {round(condition_score * 100)}%)."
        return f"Indicado para {name}."
    if rec_type == "candidato_gnn":
        return "Complementa el pack por sinergia funcional con los demás componentes."
    return "Recomendado para el perfil evaluado."


def _normalize_conditions(values: Any) -> list[str]:
    if not isinstance(values, list):
        values = [values]

    conditions = []
    seen = set()

    for value in values:
        condition = _clean_text(value)
        if condition is None or condition in seen:
            continue

        seen.add(condition)
        conditions.append(condition)

    return conditions


def _normalize_conditions_display(
    conditions: list[str],
    condition_scores: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    total = len(conditions)
    scores = condition_scores or {}

    return [
        {
            "code": condition,
            "display_name": _condition_display_name(condition),
            "level": _condition_level(
                scores.get(condition, _condition_probability_fallback(index, total))
            ),
            "probability": scores.get(condition, _condition_probability_fallback(index, total)),
            "icon_key": "check" if condition == "SALUDABLE" else "activity",
        }
        for index, condition in enumerate(conditions)
    ]


def _normalize_recommendations(values: Any, condition_scores: dict[str, float] | None = None) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []

    recommendations = []
    seen = set()

    for item in values:
        if isinstance(item, dict):
            component_id = _clean_text(item.get("component_id"))
            name = _clean_text(item.get("name") or item.get("nombre") or component_id)
            condition = _clean_text(item.get("condition") or item.get("condicion"))
            rec_type = _clean_text(item.get("type") or item.get("tipo"))
            score = _clean_float(_first_present(item.get("score"), item.get("score_gnn")))
        elif isinstance(item, (list, tuple)):
            component_id = _clean_text(item[3]) if len(item) > 3 else None
            name = _clean_text(item[0] if item else component_id)
            condition = _clean_text(item[1]) if len(item) > 1 else None
            rec_type = _clean_text(item[4]) if len(item) > 4 else None
            score = _clean_float(item[2]) if len(item) > 2 else None
        else:
            continue

        if name is None:
            continue

        dedupe_key = component_id or name.lower()
        if dedupe_key in seen:
            continue

        condition_score = (condition_scores or {}).get(condition) if condition else None
        source_ids = item.get("source_ids") if isinstance(item, dict) else []
        if not isinstance(source_ids, list):
            source_ids = []
        profile_source_ids = item.get("component_profile_source_ids") if isinstance(item, dict) else []
        if not isinstance(profile_source_ids, list):
            profile_source_ids = []
        component_lookup_candidates = item.get("component_lookup_candidates") if isinstance(item, dict) else []
        if not isinstance(component_lookup_candidates, list):
            component_lookup_candidates = []
        contraindications = item.get("contraindications") if isinstance(item, dict) else []
        if not isinstance(contraindications, list):
            contraindications = []
        life_stage_guidance = item.get("life_stage_guidance") if isinstance(item, dict) else []
        if not isinstance(life_stage_guidance, list):
            life_stage_guidance = []
        interaction_rules = item.get("interaction_rules") if isinstance(item, dict) else []
        if not isinstance(interaction_rules, list):
            interaction_rules = []
        claim_evidence = item.get("claim_evidence") if isinstance(item, dict) else []
        if not isinstance(claim_evidence, list):
            claim_evidence = []
        seen.add(dedupe_key)
        recommendations.append({
            "component_id": component_id,
            "name": name,
            "display_name": _translate_component_name(name),
            "condition": condition,
            "condition_display": _condition_display_name(condition),
            "score": score,
            "type": rec_type,
            "type_display": _type_display_name(rec_type),
            "reason": _recommendation_reason(condition, rec_type),
            "dosage_hint": _dosage_hint(name, rec_type),
            "priority": "principal" if rec_type == "semilla_directa" else "complementaria",
            "icon_key": _component_icon_key(name),
            "condition_probability": _clean_float(item.get("condition_probability")) if isinstance(item, dict) else condition_score,
            "evidence_strength": _clean_text(item.get("evidence_strength")) if isinstance(item, dict) else None,
            "evidence_type": _clean_text(item.get("evidence_type")) if isinstance(item, dict) else None,
            "evidence_weight": _clean_float(item.get("evidence_weight")) if isinstance(item, dict) else None,
            "evidence_score": _clean_float(item.get("evidence_score")) if isinstance(item, dict) else None,
            "evidence_factors": item.get("evidence_factors") if isinstance(item, dict) and isinstance(item.get("evidence_factors"), dict) else {},
            "recommendation_role": _clean_text(item.get("recommendation_role")) if isinstance(item, dict) else None,
            "requires_lab": _clean_text(item.get("requires_lab")) if isinstance(item, dict) else None,
            "risk_level": _clean_text(item.get("risk_level")) if isinstance(item, dict) else None,
            "source_quality": _clean_text(item.get("source_quality")) if isinstance(item, dict) else None,
            "missing_data_penalty": _clean_float(item.get("missing_data_penalty")) if isinstance(item, dict) else None,
            "source_ids": [str(source_id) for source_id in source_ids],
            "rationale": _clean_text(item.get("rationale")) if isinstance(item, dict) else None,
            "component_profile_role": _clean_text(item.get("component_profile_role")) if isinstance(item, dict) else None,
            "adult_upper_limit": _clean_text(item.get("adult_upper_limit")) if isinstance(item, dict) else None,
            "upper_limit_unit": _clean_text(item.get("upper_limit_unit")) if isinstance(item, dict) else None,
            "upper_limit_note": _clean_text(item.get("upper_limit_note")) if isinstance(item, dict) else None,
            "dose_guidance": _clean_text(item.get("dose_guidance")) if isinstance(item, dict) else None,
            "age_sex_note": _clean_text(item.get("age_sex_note")) if isinstance(item, dict) else None,
            "pregnancy_lactation_note": _clean_text(item.get("pregnancy_lactation_note")) if isinstance(item, dict) else None,
            "contraindications": [str(value) for value in contraindications],
            "interaction_notes": _clean_text(item.get("interaction_notes")) if isinstance(item, dict) else None,
            "component_safety_level": _clean_text(item.get("component_safety_level")) if isinstance(item, dict) else None,
            "component_profile_source_ids": [str(source_id) for source_id in profile_source_ids],
            "component_profile_rationale": _clean_text(item.get("component_profile_rationale")) if isinstance(item, dict) else None,
            "component_lookup_candidates": [str(value) for value in component_lookup_candidates],
            "life_stage_guidance": life_stage_guidance,
            "interaction_rules": interaction_rules,
            "claim_evidence": claim_evidence,
            "model2_ranker": _clean_text(item.get("model2_ranker")) if isinstance(item, dict) else None,
            "model2_stage": _clean_text(item.get("model2_stage")) if isinstance(item, dict) else None,
            "graph_similarity": _clean_float(item.get("graph_similarity")) if isinstance(item, dict) else None,
            "ranking_reason": _clean_text(item.get("ranking_reason")) if isinstance(item, dict) else None,
            "recommendation_source": _clean_text(item.get("source")) if isinstance(item, dict) else None,
            "commercial_eligible": (
                bool(item.get("commercial_eligible"))
                if isinstance(item, dict) and item.get("commercial_eligible") is not None
                else True
            ),
            "commercial_recommendation_blocked": (
                bool(item.get("commercial_recommendation_blocked"))
                if isinstance(item, dict)
                else False
            ),
            "commercial_block_reason": _clean_text(item.get("commercial_block_reason")) if isinstance(item, dict) else None,
        })

    for recommendation in recommendations:
        if recommendation.get("condition") in WELLNESS_PRIORITY_CONDITIONS:
            recommendation["commercial_eligible"] = False
            recommendation["commercial_recommendation_blocked"] = True
            recommendation["commercial_block_reason"] = (
                recommendation.get("commercial_block_reason")
                or "Prioridad blanda de bienestar: se muestra como contexto, no como producto comercial directo."
            )

    return recommendations


def _normalize_relation(item: Any) -> dict[str, str] | None:
    if isinstance(item, dict):
        component_a = _clean_text(
            item.get("component_a")
            or item.get("nombre_a")
            or item.get("name_a")
            or item.get("a")
        )
        component_b = _clean_text(
            item.get("component_b")
            or item.get("nombre_b")
            or item.get("name_b")
            or item.get("b")
        )
        relation_type = _clean_text(
            item.get("type")
            or item.get("tipo")
            or item.get("relationship_type")
            or item.get("relationship_subclass")
        )
        component_a_id = _clean_text(item.get("component_a_id"))
        component_b_id = _clean_text(item.get("component_b_id"))
        explanation = _clean_text(item.get("explanation"))
    elif isinstance(item, (list, tuple)) and len(item) >= 3:
        component_a = _clean_text(item[0])
        component_b = _clean_text(item[1])
        relation_type = _clean_text(item[2])
        component_a_id = None
        component_b_id = None
        explanation = None
    else:
        return None

    if component_a is None or component_b is None or relation_type is None:
        return None

    relation = {
        "component_a": component_a,
        "component_b": component_b,
        "type": relation_type,
    }
    if component_a_id is not None:
        relation["component_a_id"] = component_a_id
    if component_b_id is not None:
        relation["component_b_id"] = component_b_id
    if explanation is not None:
        relation["explanation"] = explanation
    return relation


def _normalize_relations(values: Any) -> list[dict[str, str]]:
    if not isinstance(values, list):
        return []

    relations = []
    seen = set()

    for item in values:
        relation = _normalize_relation(item)
        if relation is None:
            continue

        dedupe_key = (
            relation["component_a"].lower(),
            relation["component_b"].lower(),
            relation["type"].lower(),
        )
        if dedupe_key in seen:
            continue

        seen.add(dedupe_key)
        relations.append(relation)

    return relations


def _normalize_pack_components(pack: dict[str, Any]) -> list[dict[str, str | None]]:
    raw_components = pack.get("components")

    if isinstance(raw_components, list):
        components = []
        for component in raw_components:
            if isinstance(component, dict):
                component_id = _clean_text(component.get("component_id") or component.get("id"))
                name = _clean_text(component.get("name") or component.get("nombre") or component_id)
            else:
                component_id = None
                name = _clean_text(component)

            if name is not None:
                components.append({
                    "component_id": component_id,
                    "name": name,
                    "display_name": _translate_component_name(name),
                    "icon_key": _component_icon_key(name),
                })

        if components:
            return components

    component_ids = pack.get("component_ids") or []
    component_names = pack.get("component_names") or []

    if not isinstance(component_ids, list):
        component_ids = []

    if not isinstance(component_names, list):
        component_names = []

    total = max(len(component_ids), len(component_names))
    components = []

    for index in range(total):
        component_id = _clean_text(component_ids[index]) if index < len(component_ids) else None
        name = _clean_text(component_names[index]) if index < len(component_names) else component_id

        if name is not None:
            components.append({
                "component_id": component_id,
                "name": name,
                "display_name": _translate_component_name(name),
                "icon_key": _component_icon_key(name),
            })

    return components


def _normalize_packs(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []

    packs = []

    for index, item in enumerate(values, start=1):
        if not isinstance(item, dict):
            continue

        components = _normalize_pack_components(item)
        component_ids = [
            component["component_id"]
            for component in components
            if component.get("component_id") is not None
        ]
        component_names = [component["name"] for component in components]
        score_final = _clean_float(_first_present(item.get("score_final"), item.get("score")))

        packs.append({
            "pack_id": _clean_text(item.get("pack_id")) or f"pack_{index}",
            "rank": _clean_int(item.get("rank"), index),
            "title": " + ".join(component_names),
            "subtitle": f"{len(component_names)} suplemento(s) priorizados para tu perfil",
            "components": components,
            "component_ids": component_ids,
            "component_names": component_names,
            "score": score_final,
            "score_final": score_final,
            "score_gnn": _clean_float(item.get("score_gnn")),
            "score_coverage": _clean_float(item.get("score_coverage")),
            "score_feedback": _clean_float(item.get("score_feedback")),
            "feedback_count": _clean_int(item.get("feedback_count")),
            "cta_label": "Ver detalle del pack",
        })

    return packs


def _attach_products_to_recommendations(
    recommendations: list[dict[str, Any]],
    product_catalog: ProductCatalogService,
) -> list[dict[str, Any]]:
    for recommendation in recommendations:
        if recommendation.get("commercial_eligible") is False:
            recommendation["products"] = []
            recommendation["commercial_recommendation_blocked"] = True
            recommendation["commercial_block_reason"] = (
                recommendation.get("commercial_block_reason")
                or "El Modelo 2 marcó este componente como no comercializable para este perfil."
            )
            continue

        if recommendation.get("recommendation_role") == "safety_context":
            recommendation["products"] = []
            recommendation["commercial_recommendation_blocked"] = True
            recommendation["commercial_block_reason"] = (
                "Componente mostrado solo como contexto de seguridad; "
                "no se adjuntan productos comerciales."
            )
            continue

        blocking_interactions = [
            interaction
            for interaction in recommendation.get("interaction_rules", [])
            if isinstance(interaction, dict)
            and interaction.get("severity") == "high"
            and interaction.get("action") in {
                "block",
                "block_commercial",
                "block_or_warn",
                "warn_or_block",
            }
        ]
        if blocking_interactions:
            recommendation["products"] = []
            recommendation["commercial_recommendation_blocked"] = True
            recommendation["commercial_block_reason"] = str(blocking_interactions[0].get("message") or "")
            continue

        recommendation["products"] = product_catalog.products_for_component(
            recommendation.get("component_id")
        )

    return recommendations


def _attach_products_to_packs(
    packs: list[dict[str, Any]],
    product_catalog: ProductCatalogService,
) -> list[dict[str, Any]]:
    for pack in packs:
        component_ids = [
            str(component_id)
            for component_id in pack.get("component_ids", [])
            if component_id
        ]
        pack["selected_products"] = product_catalog.select_products_for_pack(component_ids)

    return packs


class RecommendationService:
    def __init__(self, models: dict, db: Session | None = None):
        self.models = models
        self.db = db
        self.feature_builder = FeatureBuilder()
        self.product_catalog = ProductCatalogService(db=db)

    def recommend(self, encuesta: EncuestaInput, user: User | None = None) -> dict:
        pipeline = self.models.get("pipeline_vitaminas")

        if pipeline is None:
            raise ModelNotLoadedError()

        try:
            payload = self.feature_builder.build_pipeline_payload(encuesta)
            # Pass lab results to Model 1 MVP so observed_lab signals activate
            lab_analysis = _lab_analysis_for_survey(encuesta)
            if lab_analysis:
                for bm in lab_analysis.get("biomarkers") or []:
                    payload[f"lab_{bm['code']}_status"] = bm.get("status", "missing")
            # Pass security context so Model 2 interaction rules evaluate correctly
            payload["condiciones_seguridad"] = list(getattr(encuesta, "condiciones_seguridad", []) or [])
            payload["restricciones"] = list(getattr(encuesta, "restricciones", []) or [])
            payload["restricciones_alergias"] = list(getattr(encuesta, "restricciones", []) or [])
            payload["suplementos_actuales"] = list(getattr(encuesta, "suplementos_actuales", []) or [])
            resultado = pipeline(payload, verbose=False)
            resultado = _to_builtin(resultado)
        except (FileNotFoundError, ModuleNotFoundError, ImportError, OSError) as exc:
            raise RecommendationGenerationError() from exc
        except Exception as exc:
            raise RecommendationGenerationError() from exc

        condition_scores = _to_builtin(resultado.get("condition_scores", {}))
        condition_details = _to_builtin(resultado.get("condition_details", []))
        explainability   = _to_builtin(resultado.get("explainability", []))

        conditions = _normalize_conditions(
            _first_present(resultado.get("condiciones"), resultado.get("conditions"), [])
        )
        condition_results, wellness_priorities, safety_flags = _categorized_condition_results(
            conditions,
            condition_scores,
            condition_details,
        )
        recommendations = _normalize_recommendations(
            _first_present(resultado.get("recomendaciones"), resultado.get("recommendations"), []),
            condition_scores=condition_scores,
        )
        packs_ranked = _normalize_packs(resultado.get("packs_ranked", []))
        recommendations = _merge_lab_supplement_signals(recommendations, lab_analysis)
        self.product_catalog.budget_min = getattr(encuesta, "presupuesto_min", None)
        self.product_catalog.budget_max = getattr(encuesta, "presupuesto_max", None)
        self.product_catalog.restrictions = getattr(encuesta, "restricciones", []) or []
        self.product_catalog.safety_conditions = getattr(encuesta, "condiciones_seguridad", []) or []
        safety_level = _combine_safety_level(_safety_level(encuesta), lab_analysis)
        commercial_recommendations_blocked = (
            safety_level == "medical_review_required"
            or bool(lab_analysis and lab_analysis.get("commercial_recommendations_blocked"))
        )
        if commercial_recommendations_blocked:
            recommendations = [
                {
                    **item,
                    "products": [],
                    "commercial_eligible": False,
                    "commercial_recommendation_blocked": True,
                    "commercial_block_reason": "Perfil crítico: requiere revisión profesional antes de productos comerciales.",
                }
                for item in recommendations
            ]
            packs_ranked = [{**pack, "selected_products": [], "score_products": None} for pack in packs_ranked]
        else:
            recommendations = _attach_products_to_recommendations(
                recommendations,
                self.product_catalog,
            )
            packs_ranked = _attach_products_to_packs(
                packs_ranked,
                self.product_catalog,
            )
            if self.db is not None:
                packs_ranked = RecommendationMetricsRepository(self.db).apply_metrics_to_packs(packs_ranked)
        recommendations = _annotate_current_supplements(recommendations, encuesta)
        packs_ranked = _filter_pack_products_for_current_supplements(packs_ranked, encuesta)

        session_id = f"ses_{uuid4().hex}"
        recommendation_id = _clean_text(resultado.get("recommendation_id")) or f"rec_{uuid4().hex}"
        model_versions = {
            "model1": "condition_mvp_model.pkl" if condition_details else "modelo1_pipeline.pkl",
            "model2": "modelo2_artifacts.pkl",
            "model2_ranker": str(resultado.get("model2_ranker_version") or "component_ranker_v2"),
            "reranker": "feedback_reranker.py",
        }
        profile_warnings = _profile_warnings(encuesta)
        if lab_analysis:
            for warning in lab_analysis.get("warnings", []):
                if warning not in profile_warnings:
                    profile_warnings.append(warning)
        safety_actions = _safety_actions(encuesta)
        if lab_analysis:
            for action in lab_analysis.get("safety_actions", []):
                if action not in safety_actions:
                    safety_actions.append(action)

        response = {
            "session_id": session_id,
            "recommendation_id": recommendation_id,
            "conditions": conditions,
            "conditions_display": _normalize_conditions_display(conditions, condition_scores),
            "explainability": explainability,
            "recommendations": recommendations,
            "packs_ranked": packs_ranked,
            "sinergias": _normalize_relations(resultado.get("sinergias", [])),
            "alertas": _normalize_relations(resultado.get("alertas", [])),
            "combo_seguro": resultado.get("combo_seguro", True),
            "mensaje": resultado.get("mensaje", "OK"),
            "disclaimer": DISCLAIMER,
            "profile_warnings": profile_warnings,
            "safety_level": safety_level,
            "safety_actions": safety_actions,
            "commercial_recommendations_blocked": commercial_recommendations_blocked,
            "condition_results": condition_results,
            "wellness_priorities": wellness_priorities,
            "safety_flags": safety_flags,
            "lab_analysis": lab_analysis,
            "model_versions": model_versions,
        }

        log_event(
            "recommendation_generated",
            recommendation_id=recommendation_id,
            user_id=str(user.id) if user else None,
            conditions=conditions,
            recommendation_count=len(recommendations),
            pack_count=len(packs_ranked),
            safety_level=safety_level,
            commercial_recommendations_blocked=commercial_recommendations_blocked,
        )
        metrics.record_domain_event("recommendation_generated", safety_level)
        if commercial_recommendations_blocked:
            metrics.record_domain_event("recommendation_commercial_block", "blocked")

        if self.db is not None:
            if user is not None:
                UserRepository(self.db).update_profile(user, _survey_profile_values(encuesta))

            RecommendationRepository(self.db).save_response(
                recommendation_id=recommendation_id,
                session_id=session_id,
                input_payload=encuesta.model_dump(),
                conditions=conditions,
                model_versions=model_versions,
                profile_warnings=profile_warnings,
                recommendations=recommendations,
                packs_ranked=packs_ranked,
                user_id=user.id if user else None,
            )

        return response
