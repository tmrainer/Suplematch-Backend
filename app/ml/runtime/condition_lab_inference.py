"""Inferencia del modelo real `condition_lab_model.pkl` (NHANES): probabilidad de laboratorio fuera de rango
a partir de la encuesta, sin usar laboratorios como entrada.

Se expone como `lab_risk_estimates` en la respuesta de /recommend con `score_basis="model_real"`. No
reemplaza al Modelo 1 basado en reglas; convive con el mientras se valida en poblacion peruana.
Si el artefacto no existe, devuelve lista vacia.
"""

from __future__ import annotations

import logging
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.config import settings

logger = logging.getLogger(__name__)

MODEL_FILENAME = "condition_lab_model.pkl"

TARGET_TO_CONDITION = {
    "target_vitamin_d_low": "DEFICIT_VIT_D",
    "target_ferritin_low": "DEFICIT_HIERRO",
    "target_anemia": "DEFICIT_HIERRO",
    "target_glucose_high": "RIESGO_METABOLICO_GLUCOSA",
    "target_cholesterol_high": "RIESGO_DISLIPIDEMIA",
    "target_hdl_low": "RIESGO_DISLIPIDEMIA",
    "target_alt_high": "SAFETY_HEPATICA",
    "target_hba1c_high": "RIESGO_METABOLICO_GLUCOSA",
    "target_b12_low": "DEFICIT_B12",
}
# Lo que ve el usuario: nombre en lenguaje comun (sin siglas, unidades ni cortes), el examen tal como se pide en un
# laboratorio peruano y el corte tecnico aparte (test_labels_are_plain_language).
TARGET_LABELS = {
    "target_vitamin_d_low": "Vitamina D baja",
    "target_ferritin_low": "Reservas de hierro bajas",
    "target_anemia": "Anemia",
    "target_glucose_high": "Azúcar en sangre alta en ayunas",
    "target_cholesterol_high": "Colesterol alto",
    "target_hdl_low": "Colesterol bueno bajo",
    "target_alt_high": "Enzima del hígado alta",
    "target_hba1c_high": "Azúcar en sangre alta en los últimos meses",
    "target_b12_low": "Vitamina B12 baja",
}
TARGET_EXAMS = {
    "target_vitamin_d_low": "Vitamina D (25-hidroxivitamina D)",
    "target_ferritin_low": "Ferritina",
    "target_anemia": "Hemograma completo",
    "target_glucose_high": "Glucosa en ayunas",
    "target_cholesterol_high": "Perfil lipídico",
    "target_hdl_low": "Perfil lipídico (colesterol HDL)",
    "target_alt_high": "Perfil hepático (TGP)",
    "target_hba1c_high": "Hemoglobina glicosilada (HbA1c)",
    "target_b12_low": "Vitamina B12 en sangre",
}
TARGET_CUTOFFS = {
    "target_vitamin_d_low": "< 20 ng/mL",
    "target_ferritin_low": "< 30 ng/mL",
    "target_anemia": "hemoglobina < 13 g/dL en hombres, < 12 g/dL en mujeres (OMS 2024)",
    "target_glucose_high": ">= 100 mg/dL",
    "target_cholesterol_high": ">= 200 mg/dL",
    "target_hdl_low": "HDL < 40 mg/dL",
    "target_alt_high": "TGP/ALT > 40 U/L",
    "target_hba1c_high": "HbA1c >= 5.7 %",
    "target_b12_low": "< 300 pg/mL",
}

# Targets excluidos de produccion y por que. Validacion peruana con ENDES 2022/2024 (28 947 y 27 464 mujeres 18-49
# con hemoglobina medida): el modelo NHANES obtuvo AUC 0.50 (azar); recalibrar no ayudo (0.50) y un modelo nativo
# ENDES llego solo a 0.57. La anemia en mujeres peruanas no se infiere desde estas variables de encuesta.
# Ver docs/condition_lab_model.md y data/reports/condition_model/endes_anemia_validation.json.
# El resto (2026-10-24): metricas en test temporal y en NHANES 2021-2023 sin reentrenar (docs/fuentes_datos_reales.md).
EXCLUDED_TARGETS: dict[str, str] = {
    "target_anemia": "no validado en Peru (ENDES 2022-2024: AUC 0.50); sugerir hemograma en vez de estimar",
    "target_glucose_high": "reemplazado por target_hba1c_high (AUC 0.844 test / 0.834 externo frente a 0.762 / 0.748; HbA1c no exige ayuno)",
    "target_ferritin_low": "no util desde la encuesta (AUC 0.575 test / 0.581 externo)",
    "target_cholesterol_high": "debil y descalibrado fuera de muestra (AUC 0.632, Brier peor que la base en 2021-2023)",
    "target_b12_low": "debil (AUC 0.687 en NHANES 2013-2014) y casi sin positivos al umbral (F1 0.01)",
}

EDAD_MAP = {"menos_18": 17.0, "18_30": 24.0, "31_50": 40.0, "mas_50": 60.0}
SUENO_HORAS = {"menos_5h": 4.5, "5_7h": 6.0, "7_9h": 8.0, "mas_9h": 9.5}
ALCOHOL_TRAGOS_DIA = {"frecuente": 2.0, "ocasional": 0.3, "raro": 0.05, "nunca": 0.0}


def model_available() -> bool:
    return (Path(settings.MODEL_DIR) / MODEL_FILENAME).exists()


@lru_cache(maxsize=1)
def load_model() -> dict[str, Any]:
    import joblib

    return joblib.load(Path(settings.MODEL_DIR) / MODEL_FILENAME)


def _num(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return math.nan
    return number if math.isfinite(number) else math.nan


def _dose(encuesta: Any, supplement: str, unit_factor: dict[str, float] | None = None) -> float:
    doses = getattr(encuesta, "suplementos_dosis_actual", {}) or {}
    dose = doses.get(supplement) if isinstance(doses, dict) else None
    if not dose:
        return math.nan
    amount = _num(getattr(dose, "amount", None) if not isinstance(dose, dict) else dose.get("amount"))
    unit = str(getattr(dose, "unit", None) if not isinstance(dose, dict) else dose.get("unit") or "").lower()
    if unit_factor:
        for key, factor in unit_factor.items():
            if key in unit:
                return amount * factor
    return amount


def survey_to_nhanes_features(encuesta: Any) -> dict[str, Any]:
    """Mapea la encuesta SupleMatch al contrato de features del modelo NHANES.

    Lo que la encuesta no pregunta (etnia, educacion, ingreso, nutrientes de la dieta detallados) va como
    faltante; el pipeline imputa con mediana + indicador de faltante. `tabaco` y `salud_autopercibida` son
    opcionales en la encuesta desde el contrato 2026-10-23.1 y usan el mismo vocabulario que el modelo.
    """
    safety = set(getattr(encuesta, "condiciones_seguridad", []) or [])
    sexo = getattr(encuesta, "sexo", None) or "missing"
    edad = _num(getattr(encuesta, "age_years", None))
    if math.isnan(edad):
        edad = EDAD_MAP.get(str(getattr(encuesta, "edad_rango", "")), math.nan)
    ejercicio = str(getattr(encuesta, "frecuencia_ejercicio", "") or "")
    alcohol_week = _num(getattr(encuesta, "alcohol_drinks_week", None))
    alcohol = alcohol_week / 7.0 if not math.isnan(alcohol_week) else ALCOHOL_TRAGOS_DIA.get(str(getattr(encuesta, "alcohol", "")), math.nan)
    sleep_quality = getattr(encuesta, "sleep_quality", None)
    current = set(getattr(encuesta, "suplementos_actuales", []) or [])
    # La pregunta de medicamentos se muestra a quien tiene diabetes medicada, medicacion cronica o 50+ anos; fuera de
    # ese grupo se asume que no los toma (la misma suposicion que hace la compuerta de la encuesta).
    medications = set(getattr(encuesta, "medicamentos_b12", []) or [])
    return {
        "sexo": sexo,
        "edad": edad,
        "etnia": "missing",
        "educacion": "missing",
        "embarazo": "no_aplica" if sexo == "masculino" else ("si" if "embarazo_lactancia" in safety else "no"),
        "ingreso_ratio": math.nan,
        "bmi": _num(getattr(encuesta, "bmi", None)),
        "peso_kg": _num(getattr(encuesta, "weight_kg", None)),
        "talla_cm": _num(getattr(encuesta, "height_cm", None)),
        "sup_count": float(len(current)),
        "sup_vit_d_mcg": _dose(encuesta, "vitamina_d", {"ui": 0.025, "iu": 0.025, "mcg": 1.0, "µg": 1.0}) if "vitamina_d" in current else 0.0,
        "sup_hierro_mg": _dose(encuesta, "hierro") if "hierro" in current else 0.0,
        "sup_b12_mcg": _dose(encuesta, "vitamina_b12", {"mcg": 1.0, "µg": 1.0, "mg": 1000.0}) if "vitamina_b12" in current else 0.0,
        "sup_folico_mcg": math.nan,
        "sup_calcio_mg": _dose(encuesta, "calcio") if "calcio" in current else 0.0,
        "sup_magnesio_mg": _dose(encuesta, "magnesio") if "magnesio" in current else 0.0,
        "sup_zinc_mg": _dose(encuesta, "zinc") if "zinc" in current else 0.0,
        "sup_vit_c_mg": _dose(encuesta, "vitamina_c") if "vitamina_c" in current else 0.0,
        "dieta_kcal": math.nan,
        "dieta_proteina_g": _num(getattr(encuesta, "protein_g_day_estimate", None)),
        "dieta_vit_d_mcg": math.nan,
        "dieta_hierro_mg": math.nan,
        "dieta_b12_mcg": math.nan,
        "dieta_folato_mcg": math.nan,
        "dieta_calcio_mg": math.nan,
        "dieta_magnesio_mg": math.nan,
        "dieta_zinc_mg": math.nan,
        "dieta_vit_c_mg": math.nan,
        "dieta_fibra_g": math.nan,
        "fuma": str(getattr(encuesta, "tabaco", None) or "missing"),
        "actividad_vigorosa": "si" if ejercicio in {"3_4_semana", "diario"} else ("no" if ejercicio else "missing"),
        "actividad_moderada": "si" if ejercicio in {"1_2_semana", "3_4_semana", "diario"} else ("no" if ejercicio else "missing"),
        "alcohol_tragos_dia": alcohol,
        "diabetes_dx": "si" if "diabetes_medicada" in safety else "missing",
        "sueno_horas": SUENO_HORAS.get(str(getattr(encuesta, "horas_sueno", "")), math.nan),
        "sueno_problemas": "si" if sleep_quality == "mala" else ("no" if sleep_quality == "buena" else "missing"),
        "salud_autopercibida": str(getattr(encuesta, "salud_autopercibida", None) or "missing"),
        "metformina": "si" if "metformina" in medications else "no",
        "antiacidos": "si" if "antiacidos_ibp" in medications else "no",
    }


def predict_lab_risks(encuesta: Any) -> list[dict[str, Any]]:
    if not model_available():
        return []
    try:
        artifact = load_model()
    except Exception as exc:  # artefacto corrupto o version incompatible
        logger.warning("condition_lab_model no cargo: %s", exc)
        return []
    features = survey_to_nhanes_features(encuesta)
    columns = list(artifact["cat_features"]) + list(artifact["num_features"])
    row = pd.DataFrame([{col: features.get(col, math.nan) for col in columns}])
    out: list[dict[str, Any]] = []
    for target, pipeline in artifact["models"].items():
        if target in EXCLUDED_TARGETS:
            continue
        try:
            probability = float(pipeline.predict_proba(row)[0, 1])
        except Exception as exc:
            logger.warning("condition_lab_model %s fallo: %s", target, exc)
            continue
        threshold = float(artifact["thresholds"].get(target, 0.5))
        out.append(
            {
                "target": target,
                "label": TARGET_LABELS.get(target, target),
                "exam_name": TARGET_EXAMS.get(target),
                "cutoff": TARGET_CUTOFFS.get(target),
                "condition": TARGET_TO_CONDITION.get(target),
                "probability": round(probability, 4),
                "score_semantics": "probabilidad_calibrada_real",
                "threshold": threshold,
                "positive": probability >= threshold,
                "score_basis": "model_real",
                "model": MODEL_FILENAME,
                "train_data": "NHANES {} (test {})".format(
                    *(artifact.get("target_splits") or {}).get(target, (artifact.get("train_cycle"), artifact.get("test_cycle")))
                ),
                "note": "Probabilidad calibrada en poblacion de EE. UU.; no validada en Peru. Sugiere confirmar con examen.",
            }
        )
    out.sort(key=lambda item: item["probability"], reverse=True)
    return out
