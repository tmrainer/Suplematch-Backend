from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from app.core.config import settings
from app.ml.features_contract import (
    CAT_COLS,
    DIET_QUANTITY_COLS,
    DIET_STATUS_COLS,
    FEATURE_CONTRACT_VERSION,
    LAB_BENCHMARK_STATUS_COLS,
    LAB_STATUS_COLS,
    MEDICAL_SAFETY_COLS,
    MISSING_CATEGORY,
    NUM_COLS,
    PROFILE_CONTEXT_COLS,
    SOFT_SIGNAL_COLS,
    SURVEY_CONTEXT_COLS,
    SYMPTOM_COLS,
    aggregate_rule_score,
    is_corroborated,
    prepare_features,
    rule_matches,
)

logger = logging.getLogger(__name__)

MODEL_FILENAME = "condition_mvp_model.pkl"

# Alias conservados para scripts de training/benchmark que importan los nombres privados.
_prepare_features = prepare_features
_rule_matches = rule_matches

# Las reglas de contexto de bienestar (visual, digestiva, fatiga, hidratacion, cardiovascular, cognitiva) vivian
# aqui, duplicadas respecto de condition_rules.csv. Desde 2026-10-24 estan en el CSV (unica fuente): el modelo las
# aprende en entrenamiento y la agregacion por familia evita contar dos veces el mismo hecho.

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


# Segunda opinion del modelo real (NHANES, condition_lab_model) para condiciones limitrofes. Solo para targets con
# AUC util (vitamina D: 0.70 con encuestas como las de SupleMatch en NHANES 2013-2014; ferritina 0.58 queda fuera).
# Ver apply_second_opinion.
SECOND_OPINION_TARGETS: dict[str, str] = {"DEFICIT_VIT_D": "target_vitamin_d_low"}
SECOND_OPINION_MARGIN = 0.15
# Familias de evidencia de la encuesta que el modelo real no ve (NHANES no pregunta por exposicion solar). Una de
# ellas + estimacion positiva del modelo real son dos evidencias independientes: confirman sin exigir el margen.
SECOND_OPINION_COMPLEMENTARY_FAMILIES: dict[str, frozenset[str]] = {
    "DEFICIT_VIT_D": frozenset({"sun", "sun_barrier"}),
}

# Quien ya toma el suplemento que corrige el deficit no recibe la marca solo por la encuesta; con un examen observado
# si. NHANES 2013-2014: 15 % con vitamina D < 20 ng/mL entre quienes la toman (incluye multivitaminicos) frente a 44 %
# entre quienes no (docs/precision_nhanes_2013_2014.md). La segunda opinion tampoco la reactiva.
SUPPLEMENTS_SUPPRESSING_CONDITION: dict[str, frozenset[str]] = {
    "DEFICIT_VIT_D": frozenset({"vitamina_d", "multivitaminico"}),
}

# Ningun umbral de decision puede bajar de este valor aunque la calibracion sobre NHANES lo sugiera
# (llego a 0.05 para RIESGO_SALUD_OSEA, lo que marca positivo a casi cualquier perfil).
MIN_DECISION_THRESHOLD = 0.30


@lru_cache(maxsize=1)
def load_condition_mvp_model() -> dict[str, Any]:
    path = Path(settings.MODEL_DIR) / MODEL_FILENAME
    artifact = joblib.load(path)
    _warn_on_contract_drift(artifact, path)
    return artifact


def _warn_on_contract_drift(artifact: dict[str, Any], path: Path) -> None:
    """Loguea (sin fallar) si el .pkl fue entrenado con otra version del contrato de features."""
    trained_version = artifact.get("feature_contract_version")
    if trained_version != FEATURE_CONTRACT_VERSION:
        logger.warning(
            "condition_mvp_model: feature_contract_version del artefacto (%s) difiere de la actual (%s); "
            "reentrenar con scripts/training/entrenar_modelo_condiciones.py. path=%s",
            trained_version,
            FEATURE_CONTRACT_VERSION,
            path,
        )
    if list(artifact.get("cat_cols", [])) != CAT_COLS or list(artifact.get("num_cols", [])) != NUM_COLS:
        logger.warning(
            "condition_mvp_model: cat_cols/num_cols del artefacto no coinciden con app.ml.features_contract; "
            "el modelo se usara con las columnas guardadas en el .pkl. path=%s",
            path,
        )


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


def predict_condition_probabilities(features: dict[str, Any], artifact: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """``artifact`` permite evaluar otro modelo (p. ej. la prueba de estabilidad entre semillas); por defecto el servido."""
    artifact = artifact or load_condition_mvp_model()
    labels: list[str] = artifact["labels"]
    cat_cols: list[str] = artifact["cat_cols"]
    num_cols: list[str] = artifact["num_cols"]
    thresholds: dict[str, float] = artifact["thresholds"]
    pipeline = artifact["pipeline"]
    condition_rules: dict[str, list[dict[str, Any]]] = artifact.get("condition_rules", {})
    condition_requirements: dict[str, dict[str, Any]] = artifact.get("condition_requirements", {})
    # Artefactos anteriores a 2026-10-24 se entrenaron con suma simple; se respeta su modo.
    aggregation = artifact.get("rule_aggregation", "sum")
    rule_threshold_by_label: dict[str, float] = artifact.get("rule_thresholds", {})

    row_payload = _prepare_features(features, cat_cols, num_cols)
    row = pd.DataFrame([row_payload])[cat_cols + num_cols]
    probabilities = pipeline.predict_proba(row)[0]

    response = []
    for label, probability in zip(labels, probabilities):
        threshold = max(float(thresholds[label]), MIN_DECISION_THRESHOLD)
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
        rule_score, rule_families = aggregate_rule_score(matched_rule_details, aggregation)
        corroborated = is_corroborated(rule_families, aggregation)
        model_probability = float(probability)
        calibrated_by_rules = False
        final_probability = model_probability
        # El puntaje de reglas se compara con su propio umbral (conditions.csv, escalado en modo "family"); los
        # artefactos anteriores no lo traen y usan el umbral del modelo, como antes.
        rule_threshold = float(rule_threshold_by_label.get(label, threshold))
        if rule_score >= rule_threshold and model_probability < threshold and corroborated:
            final_probability = min(0.98, threshold + min(0.12, max(0.03, rule_score - threshold)))
            calibrated_by_rules = True
        requirement = condition_requirements.get(label, {})
        missing_data = [
            item
            for item in requirement.get("needs_lab_fields", [])
            if row_payload.get(f"lab_{item}_status") == MISSING_CATEGORY
        ]
        signal_groups = _signal_groups_from_rules(matched_rule_details)
        taking = SUPPLEMENTS_SUPPRESSING_CONDITION.get(label, frozenset()) & set(features.get("suplementos_actuales") or [])
        suppressed_by = sorted(taking)[0] if taking and "observed_lab" not in signal_groups else None
        primary_signal_group = _primary_signal_group(signal_groups)
        evidence_level = _evidence_level(primary_signal_group, signal_groups, label.startswith("SAFETY_"))
        signal_strength = _signal_strength(primary_signal_group, signal_groups, rule_score)
        response.append(
            {
                "condition": label,
                "probability": round(float(final_probability), 4),
                "model_probability": round(model_probability, 4),
                "threshold": threshold,
                # Sin laboratorio hacen falta dos familias de evidencia: el modelo tampoco puede marcar con una.
                "positive": bool(float(final_probability) >= threshold and corroborated) and suppressed_by is None,
                "suppressed_by_supplement": suppressed_by,
                "corroborated": corroborated,
                "rule_families": rule_families,
                "rule_aggregation": aggregation,
                "drivers": sorted(set(matched_rules)),
                "driver_details": matched_rule_details,
                "missing_data": sorted(set(missing_data)),
                "evidence_level": evidence_level,
                "primary_signal_group": primary_signal_group,
                "signal_strength": signal_strength,
                "signal_groups": signal_groups,
                "rule_score": rule_score,
                "rule_threshold": rule_threshold,
                "calibrated_by_rules": calibrated_by_rules,
                # Origen del score final: "model" (regresion logistica entrenada con datos sinteticos),
                # "model+rules" (las reglas elevaron el score por encima del modelo). Nunca es una
                # probabilidad clinica; ver docs/plan_fiabilidad.md Fase 3.
                "score_basis": "model+rules" if calibrated_by_rules else "model",
                "final_score": round(float(final_probability), 4),
                "safety_flag": label.startswith("SAFETY_"),
            }
        )

    response.sort(key=lambda item: item["probability"], reverse=True)
    return response


def second_opinion_from_lab_risks(lab_risks: list[dict[str, Any]]) -> dict[str, float]:
    """Condiciones con estimacion positiva del modelo real, solo para los targets habilitados."""
    by_target = {item.get("target"): item for item in lab_risks or []}
    return {
        condition: float(by_target[target]["probability"])
        for condition, target in SECOND_OPINION_TARGETS.items()
        if target in by_target and by_target[target].get("positive")
    }


def apply_second_opinion(details: list[dict[str, Any]], second_opinion: dict[str, float] | None) -> list[dict[str, Any]]:
    """Desempate con el modelo real para condiciones limitrofes.

    Una condicion no detectada pasa a positiva solo si el modelo real (NHANES) la estima positiva y ademas:

    - ``borderline``: la encuesta la confirma con dos familias de evidencia y el puntaje de reglas queda a menos de
      ``SECOND_OPINION_MARGIN`` de su umbral; o
    - ``complementary_family``: la encuesta aporta una familia que el modelo real no ve
      (``SECOND_OPINION_COMPLEMENTARY_FAMILIES``, p. ej. poco sol para vitamina D). Son dos evidencias
      independientes: demografia/dieta/suplementos por el modelo real y exposicion solar por la encuesta.

    El modelo real nunca marca solo (no ve exposicion solar ni datos de Peru). El indice mostrado pasa a ser la
    probabilidad calibrada del modelo real y ``second_opinion_reason`` indica la via.
    """
    if not second_opinion:
        return details
    updated = []
    for item in details:
        probability = second_opinion.get(item["condition"])
        reason = None
        if probability is not None and not item.get("positive") and not item.get("suppressed_by_supplement"):
            rule_threshold = float(item.get("rule_threshold", item.get("threshold", 1.0)))
            complementary = SECOND_OPINION_COMPLEMENTARY_FAMILIES.get(item["condition"], frozenset())
            if item.get("corroborated", False) and float(item.get("rule_score", 0.0)) >= rule_threshold - SECOND_OPINION_MARGIN:
                reason = "borderline"
            elif complementary & set(item.get("rule_families") or {}):
                reason = "complementary_family"
        if reason:
            item = {
                **item,
                "positive": True,
                "probability": round(max(float(item["probability"]), probability), 4),
                "final_score": round(max(float(item["probability"]), probability), 4),
                "second_opinion_probability": probability,
                "second_opinion_reason": reason,
                "score_basis": "rules+second_opinion_nhanes",
            }
        updated.append(item)
    return updated

