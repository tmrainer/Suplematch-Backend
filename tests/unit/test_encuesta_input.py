import pytest
from pydantic import ValidationError

from app.ml.feature_builder import FeatureBuilder
from app.schemas.encuesta import EncuestaInput


def _payload(**overrides):
    data = {
        "edad_rango": "31_50",
        "horas_sueno": "5_7h",
        "frecuencia_ejercicio": "1_2_semana",
        "dieta": "regular",
        "fatiga": "a_menudo",
        "exposicion_solar": "menos_15min",
        "frecuencia_enfermedad": "1_2_anio",
        "estres": "moderado",
        "alcohol": "ocasional",
    }
    data.update(overrides)
    return data


def test_current_supplements_are_required_when_user_takes_them():
    with pytest.raises(ValidationError):
        EncuestaInput(**_payload(toma_suplementos="si", suplementos_actuales=[]))


def test_current_supplements_are_rejected_when_user_says_no():
    with pytest.raises(ValidationError):
        EncuestaInput(**_payload(toma_suplementos="no", suplementos_actuales=["vitamina_d"]))


def test_exclusive_answers_cannot_be_combined():
    with pytest.raises(ValidationError):
        EncuestaInput(**_payload(restricciones=["sin_restricciones", "sin_gluten"]))

    with pytest.raises(ValidationError):
        EncuestaInput(**_payload(condiciones_seguridad=["ninguna", "medicacion_cronica"]))


def test_extended_survey_fields_feed_existing_model_features():
    encuesta = EncuestaInput(
        **_payload(
            sexo="masculino",
            tipo_dieta="vegano",
            dolor_muscular="frecuente",
            niebla_mental="severo",
            caida_cabello="moderado",
            objetivos=["energia", "cabello_piel_unas", "rendimiento"],
            toma_suplementos="si",
            suplementos_actuales=["vitamina_d"],
            restricciones=["sin_gluten"],
            condiciones_seguridad=["medicacion_cronica"],
            presupuesto="bajo",
        )
    )

    features = FeatureBuilder().build_pipeline_payload(encuesta)

    assert features["sexo"] == "M"
    assert features["tipo_dieta"] == "vegano"
    assert features["dolor_muscular"] == 4
    assert features["niebla_mental"] == 5
    assert features["caida_cabello"] == 3
    assert features["meta_energia"] == 1
    assert features["meta_belleza"] == 1
    assert features["meta_rendimiento"] == 1
