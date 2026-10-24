from __future__ import annotations

import math
from pathlib import Path

import pytest

from app.core.config import settings
from app.domains.survey.esquemas_encuesta import EncuestaInput
from app.ml.runtime import condition_lab_inference as cli


def _encuesta(**overrides) -> EncuestaInput:
    data = {
        "edad_rango": "31_50", "horas_sueno": "5_7h", "frecuencia_ejercicio": "1_2_semana", "dieta": "regular",
        "fatiga": "a_menudo", "exposicion_solar": "menos_15min", "frecuencia_enfermedad": "1_2_anio",
        "estres": "moderado", "alcohol": "ocasional",
    }
    data.update(overrides)
    return EncuestaInput(**data)


def test_survey_maps_to_full_feature_contract_without_labs() -> None:
    from scripts.training.entrenar_condiciones_nhanes import CAT_FEATURES, NUM_FEATURES

    features = cli.survey_to_nhanes_features(_encuesta(sexo="femenino", age_years=34, weight_kg=60, height_cm=165))
    assert set(features) == set(CAT_FEATURES + NUM_FEATURES)
    assert features["sexo"] == "femenino" and features["edad"] == 34.0
    assert features["sueno_horas"] == 6.0 and features["actividad_moderada"] == "si" and features["actividad_vigorosa"] == "no"
    assert math.isnan(features["dieta_kcal"])  # la encuesta no lo pregunta: se imputa


def test_pregnancy_and_diabetes_flags_come_from_safety_conditions() -> None:
    features = cli.survey_to_nhanes_features(_encuesta(sexo="femenino", condiciones_seguridad=["embarazo_lactancia", "diabetes_medicada"]))
    assert features["embarazo"] == "si" and features["diabetes_dx"] == "si"
    assert cli.survey_to_nhanes_features(_encuesta(sexo="masculino"))["embarazo"] == "no_aplica"


def test_returns_empty_when_model_missing(monkeypatch) -> None:
    monkeypatch.setattr(cli, "model_available", lambda: False)
    assert cli.predict_lab_risks(_encuesta()) == []


@pytest.mark.skipif(not (Path(settings.MODEL_DIR) / cli.MODEL_FILENAME).exists(), reason="condition_lab_model.pkl no entrenado")
def test_real_model_outputs_calibrated_probabilities_with_model_real_basis() -> None:
    cli.load_model.cache_clear()
    estimates = cli.predict_lab_risks(_encuesta(sexo="femenino", age_years=45, weight_kg=85, height_cm=160))
    assert estimates
    for item in estimates:
        assert 0.0 <= item["probability"] <= 1.0
        assert item["score_basis"] == "model_real"
        assert item["threshold"] >= 0.30


@pytest.mark.skipif(not (Path(settings.MODEL_DIR) / cli.MODEL_FILENAME).exists(), reason="condition_lab_model.pkl no entrenado")
def test_anemia_target_is_excluded_after_endes_validation() -> None:
    cli.load_model.cache_clear()
    targets = {item["target"] for item in cli.predict_lab_risks(_encuesta(sexo="femenino", age_years=30))}
    assert "target_anemia" not in targets
    assert "target_anemia" in cli.EXCLUDED_TARGETS


def test_smoking_and_self_rated_health_feed_the_real_model_features() -> None:
    """Contrato 2026-10-23.1: `tabaco` y `salud_autopercibida` dejan de ir siempre como faltantes."""
    features = cli.survey_to_nhanes_features(_encuesta(tabaco="actual", salud_autopercibida="regular"))
    assert features["fuma"] == "actual"
    assert features["salud_autopercibida"] == "regular"
    # Sin respuesta siguen como `missing` (el pipeline imputa), igual que antes del contrato nuevo.
    defaults = cli.survey_to_nhanes_features(_encuesta())
    assert defaults["fuma"] == "missing" and defaults["salud_autopercibida"] == "missing"


def test_survey_vocabulary_matches_nhanes_feature_vocabulary() -> None:
    """Los valores de la encuesta deben ser exactamente los que vio el modelo en entrenamiento."""
    from typing import get_args

    from app.domains.survey.esquemas_encuesta import SaludAutopercibida, Tabaco

    assert set(get_args(Tabaco)) == {"nunca", "ex", "actual"}
    assert set(get_args(SaludAutopercibida)) == {"excelente", "muy_buena", "buena", "regular", "mala"}


@pytest.mark.skipif(not (Path(settings.MODEL_DIR) / cli.MODEL_FILENAME).exists(), reason="condition_lab_model.pkl no entrenado")
def test_lab_risk_estimates_declare_calibrated_probability_semantics() -> None:
    cli.load_model.cache_clear()
    estimates = cli.predict_lab_risks(_encuesta(sexo="masculino", age_years=50, tabaco="actual", salud_autopercibida="mala"))
    assert estimates
    assert all(item["score_semantics"] == "probabilidad_calibrada_real" for item in estimates)
