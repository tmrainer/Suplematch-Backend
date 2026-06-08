from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline as SklearnPipeline


# ── Mapas de nombres y etiquetas ──────────────────────────────────────────────

FEATURE_LABELS: dict[str, str] = {
    # Numéricas (passthrough)
    "fatiga_general":       "Fatiga frecuente",
    "problemas_sueno":      "Problemas de sueño",
    "irritabilidad":        "Nivel de estrés",
    "enfermedad_frecuente": "Frecuencia de enfermedades",
    "niebla_mental":        "Niebla mental",
    "edad":                 "Edad",
    "dolor_muscular":       "Dolor muscular",
    "dolor_articular":      "Dolor articular",
    "calambres":            "Calambres",
    "meta_energia":         "Objetivo energía",
    "meta_inmunidad":       "Objetivo inmunidad",
    "meta_salud_osea":      "Objetivo salud ósea",
    "meta_cognitivo":       "Objetivo cognitivo",
    "meta_rendimiento":     "Objetivo rendimiento",
    # OHE — exposicion_solar
    "exposicion_solar_baja":  "Exposición solar baja",
    "exposicion_solar_media": "Exposición solar media",
    "exposicion_solar_alta":  "Exposición solar alta",
    # OHE — nivel_actividad
    "nivel_actividad_sedentario": "Actividad sedentaria",
    "nivel_actividad_moderado":   "Actividad moderada",
    "nivel_actividad_activo":     "Actividad activa",
    "nivel_actividad_muy_activo": "Actividad muy activa",
    # OHE — sexo
    "sexo_F": "Sexo femenino",
    "sexo_M": "Sexo masculino",
    # OHE — tipo_dieta
    "tipo_dieta_omnivoro":    "Dieta omnívora",
    "tipo_dieta_vegano":      "Dieta vegana",
    "tipo_dieta_vegetariano": "Dieta vegetariana",
}

VALUE_LABELS: dict[str, dict] = {
    "fatiga_general":       {1: "Casi nunca", 3: "A veces", 4: "A menudo", 5: "Siempre"},
    "problemas_sueno":      {1: "Óptimo", 2: "Leve", 4: "Deficiente (5-7h)", 5: "Severo (<5h)"},
    "irritabilidad":        {1: "Bajo", 3: "Moderado", 4: "Alto", 5: "Muy alto"},
    "enfermedad_frecuente": {1: "Casi nunca", 2: "1-2/año", 4: "3-4/año", 5: "Muy seguido"},
    "niebla_mental":        {2: "Leve", 3: "Moderada", 4: "Frecuente"},
    "exposicion_solar":     {"baja": "Menos de 15 min/día", "media": "15-60 min/día", "alta": "Más de 1h/día"},
    "nivel_actividad":      {"sedentario": "Sedentario", "moderado": "Moderado", "activo": "Activo", "muy_activo": "Muy activo"},
    "meta_salud_osea":      {0: "No priorizada", 1: "Priorizada"},
    "meta_inmunidad":       {0: "No priorizada", 1: "Priorizada"},
    "meta_energia":         {0: "No priorizada", 1: "Priorizada"},
}

# Fallback rule-based: qué features son relevantes por condición
CONDITION_FEATURE_MAP: dict[str, list[tuple[str, str, bool]]] = {
    "FATIGA": [
        ("fatiga_general",   "Fatiga frecuente",     True),
        ("problemas_sueno",  "Problemas de sueño",   True),
        ("irritabilidad",    "Nivel de estrés",       True),
    ],
    "PROBLEMAS_SUENO": [
        ("problemas_sueno",  "Calidad del sueño",    True),
        ("irritabilidad",    "Nivel de estrés",       True),
        ("fatiga_general",   "Fatiga general",        True),
    ],
    "DEFICIT_VIT_D": [
        ("exposicion_solar", "Exposición solar",      False),
        ("meta_salud_osea",  "Prioridad salud ósea",  True),
        ("edad",             "Edad",                  True),
    ],
    "DEFICIT_CALCIO": [
        ("exposicion_solar", "Exposición solar",      False),
        ("meta_salud_osea",  "Prioridad salud ósea",  True),
        ("edad",             "Edad",                  True),
    ],
    "BAJA_INMUNIDAD": [
        ("enfermedad_frecuente", "Frecuencia de enfermedades", True),
        ("meta_inmunidad",       "Objetivo inmunidad",          True),
        ("fatiga_general",       "Fatiga general",              True),
    ],
    "ESTRES": [
        ("irritabilidad",   "Nivel de estrés",       True),
        ("niebla_mental",   "Niebla mental",          True),
        ("problemas_sueno", "Problemas de sueño",    True),
    ],
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _value_label(feature: str, value: Any) -> str:
    mapping = VALUE_LABELS.get(feature, {})
    return str(mapping.get(value, value))


def _impact_from_shap(shap_val: float) -> str:
    a = abs(shap_val)
    if a > 0.15:
        return "alto"
    if a > 0.05:
        return "medio"
    return "bajo"


def _impact_from_rule(feature: str, value: Any, high_is_bad: bool) -> str:
    if isinstance(value, (int, float)):
        if high_is_bad:
            return "alto" if value >= 4 else "medio" if value >= 3 else "bajo"
        return "alto" if value <= 1 else "medio" if value <= 2 else "bajo"
    s = str(value)
    if not high_is_bad:
        return "alto" if s == "baja" else "medio" if s == "media" else "bajo"
    return "bajo"


def _get_feature_names(preprocessor: Any, fallback_cols: list[str]) -> list[str]:
    """Extract feature names after ColumnTransformer, stripping transformer prefix."""
    try:
        raw = list(preprocessor.get_feature_names_out())
        # strip transformer prefix: "cat__sexo_F" -> "sexo_F", "num__fatiga_general" -> "fatiga_general"
        return [n.split("__", 1)[-1] for n in raw]
    except Exception:
        pass
    try:
        last = preprocessor.steps[-1][1]
        raw = list(last.get_feature_names_out())
        return [n.split("__", 1)[-1] for n in raw]
    except Exception:
        pass
    return fallback_cols


def _resolve_feature(feat_name: str, user_payload: dict) -> tuple[str, Any]:
    """
    Maps a transformed feature name back to the original feature key and raw value.
    Handles OHE suffixes: "exposicion_solar_baja" -> feature="exposicion_solar", value=payload["exposicion_solar"]
    """
    # Exact match first
    if feat_name in user_payload:
        return feat_name, user_payload[feat_name]

    # OHE suffix match: try progressively shorter prefixes
    for key in sorted(user_payload.keys(), key=len, reverse=True):
        if feat_name.startswith(key + "_") or feat_name == key:
            return key, user_payload[key]

    return feat_name, None


# ── SHAP-based explainability ─────────────────────────────────────────────────

def _shap_drivers(
    pipeline: Any,
    labels: list[str],
    row_df: pd.DataFrame,
    condition_scores: dict[str, float],
    user_payload: dict,
    top_k: int = 3,
) -> list[dict] | None:
    """
    Returns SHAP-based drivers per condition.
    Returns None if shap is not installed or any step fails.
    """
    try:
        import shap  # lazy import — no crash if not installed
    except ImportError:
        return None

    try:
        steps = list(pipeline.steps)
        preprocessing_steps = steps[:-1]
        classifier = steps[-1][1]  # MultiOutputClassifier

        if preprocessing_steps:
            preprocessor = SklearnPipeline(preprocessing_steps)
            X_transformed = preprocessor.transform(row_df)
            feature_names = _get_feature_names(preprocessor, list(row_df.columns))
        else:
            X_transformed = row_df.values
            feature_names = list(row_df.columns)

        explanations = []
        for i, label in enumerate(labels):
            score = condition_scores.get(label, 0.0)
            if score < 0.45:
                continue

            estimator = classifier.estimators_[i]
            explainer = shap.TreeExplainer(estimator)
            shap_vals = explainer.shap_values(X_transformed)

            # Binary RF: list of [class0_array, class1_array]
            if isinstance(shap_vals, list) and len(shap_vals) == 2:
                vals = np.array(shap_vals[1][0])  # class 1, first sample
            else:
                vals = np.array(shap_vals[0])

            top_indices = np.argsort(np.abs(vals))[::-1][:top_k]

            drivers = []
            seen_features: set[str] = set()
            for idx in top_indices:
                shap_val = float(vals[idx])
                raw_feat = feature_names[idx] if idx < len(feature_names) else f"feature_{idx}"
                original_feature, raw_value = _resolve_feature(raw_feat, user_payload)

                if original_feature in seen_features:
                    continue
                seen_features.add(original_feature)

                drivers.append({
                    "feature":     original_feature,
                    "label":       FEATURE_LABELS.get(raw_feat) or FEATURE_LABELS.get(original_feature) or original_feature.replace("_", " ").title(),
                    "value":       raw_value,
                    "value_label": _value_label(original_feature, raw_value),
                    "impact":      _impact_from_shap(shap_val),
                    "shap_value":  round(shap_val, 4),
                })

            explanations.append({
                "condition":   label,
                "probability": score,
                "drivers":     drivers,
            })

        return explanations

    except Exception:
        return None


# ── Rule-based fallback ───────────────────────────────────────────────────────

def _rule_based_drivers(
    condition_scores: dict[str, float],
    user_payload: dict,
) -> list[dict]:
    explanations = []
    for condition, prob in sorted(condition_scores.items(), key=lambda x: -x[1]):
        if prob < 0.45:
            continue
        drivers = []
        for feat_name, feat_label, high_is_bad in CONDITION_FEATURE_MAP.get(condition, []):
            value = user_payload.get(feat_name)
            if value is None:
                continue
            drivers.append({
                "feature":     feat_name,
                "label":       feat_label,
                "value":       value,
                "value_label": _value_label(feat_name, value),
                "impact":      _impact_from_rule(feat_name, value, high_is_bad),
            })
        explanations.append({
            "condition":   condition,
            "probability": prob,
            "drivers":     drivers,
        })
    return explanations


# ── Public API ────────────────────────────────────────────────────────────────

def get_condition_scores(pipeline: Any, labels: list[str], row: pd.DataFrame) -> dict[str, float]:
    """Real per-user probabilities from Model 1 predict_proba."""
    try:
        proba_list = pipeline.predict_proba(row)
        return {
            label: round(float(proba_list[i][0][1]), 4)
            for i, label in enumerate(labels)
        }
    except Exception:
        return {}


def build_explainability(
    pipeline: Any,
    labels: list[str],
    row_df: pd.DataFrame,
    condition_scores: dict[str, float],
    user_payload: dict,
) -> list[dict]:
    """
    Tries SHAP (TreeExplainer on each RF sub-estimator).
    Falls back to rule-based mapping if SHAP is not available or fails.
    """
    result = _shap_drivers(pipeline, labels, row_df, condition_scores, user_payload)
    if result is not None:
        return result
    return _rule_based_drivers(condition_scores, user_payload)
