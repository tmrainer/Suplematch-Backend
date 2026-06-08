from __future__ import annotations

from typing import Any

import pandas as pd


CONDITION_FEATURE_MAP: dict[str, list[tuple[str, str, bool]]] = {
    # (feature_name, human_label, high_is_bad)
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

VALUE_LABELS: dict[str, dict] = {
    "fatiga_general":       {1: "Casi nunca", 3: "A veces", 4: "A menudo", 5: "Siempre"},
    "problemas_sueno":      {1: "Óptimo", 2: "Leve", 4: "Deficiente (5-7h)", 5: "Severo (<5h)"},
    "irritabilidad":        {1: "Bajo", 3: "Moderado", 4: "Alto", 5: "Muy alto"},
    "enfermedad_frecuente": {1: "Casi nunca", 2: "1-2/año", 4: "3-4/año", 5: "Muy seguido"},
    "exposicion_solar":     {"baja": "Menos de 15 min/día", "media": "15-60 min/día", "alta": "Más de 1h/día"},
    "nivel_actividad":      {"sedentario": "Sedentario", "moderado": "Moderado", "activo": "Activo", "muy_activo": "Muy activo"},
    "niebla_mental":        {2: "Leve", 3: "Moderada", 4: "Frecuente"},
    "meta_salud_osea":      {0: "No priorizada", 1: "Priorizada"},
    "meta_inmunidad":       {0: "No priorizada", 1: "Priorizada"},
}


def _value_label(feature: str, value: Any) -> str:
    mapping = VALUE_LABELS.get(feature, {})
    return str(mapping.get(value, value))


def _impact(feature: str, value: Any, high_is_bad: bool) -> str:
    if isinstance(value, (int, float)):
        if high_is_bad:
            if value >= 4:
                return "alto"
            if value >= 3:
                return "medio"
            return "bajo"
        else:
            if value <= 1:
                return "alto"
            if value <= 2:
                return "medio"
            return "bajo"
    else:
        s = str(value)
        if not high_is_bad:
            if s == "baja":
                return "alto"
            if s == "media":
                return "medio"
            return "bajo"
        return "bajo"


def get_condition_scores(pipeline: Any, labels: list[str], row: pd.DataFrame) -> dict[str, float]:
    """Returns real probability per condition from Model 1's predict_proba."""
    try:
        proba_list = pipeline.predict_proba(row)
        return {
            label: round(float(proba_list[i][0][1]), 4)
            for i, label in enumerate(labels)
        }
    except Exception:
        return {}


def build_explainability(
    condition_scores: dict[str, float],
    user_payload: dict,
) -> list[dict]:
    """
    For each detected condition (prob >= 0.45), returns the top features
    that drove that condition based on the user's survey answers.
    """
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
                "impact":      _impact(feat_name, value, high_is_bad),
            })

        explanations.append({
            "condition":  condition,
            "probability": prob,
            "drivers":    drivers,
        })

    return explanations
