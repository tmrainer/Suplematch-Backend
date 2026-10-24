from __future__ import annotations

from app.domains.recommendations.servicio_recomendaciones import _derived_safety_context, _profile_warnings, _safety_level
from app.domains.survey.esquemas_encuesta import EncuestaInput


def _encuesta(**overrides) -> EncuestaInput:
    data = {
        "edad_rango": "31_50",
        "horas_sueno": "7_9h",
        "frecuencia_ejercicio": "1_2_semana",
        "dieta": "regular",
        "fatiga": "a_veces",
        "exposicion_solar": "15_30min",
        "frecuencia_enfermedad": "1_2_anio",
        "estres": "moderado",
        "alcohol": "ocasional",
    }
    data.update(overrides)
    return EncuestaInput(**data)


def test_new_safety_codes_are_accepted_by_the_survey() -> None:
    encuesta = _encuesta(condiciones_seguridad=["diabetes_medicada", "sedantes", "hipertension"])
    assert set(encuesta.condiciones_seguridad) == {"diabetes_medicada", "sedantes", "hipertension"}
    assert _safety_level(encuesta) == "caution"
    assert any("sedantes" in w.lower() for w in _profile_warnings(encuesta))


def test_immunosuppression_requires_medical_review() -> None:
    assert _safety_level(_encuesta(condiciones_seguridad=["inmunosupresion"])) == "medical_review_required"


def test_insomnia_is_derived_from_sleep_answers_only() -> None:
    assert _derived_safety_context(_encuesta()) == []
    assert _derived_safety_context(_encuesta(sleep_quality="mala")) == ["insomnio"]
    assert _derived_safety_context(_encuesta(night_wakeups="3_o_mas")) == ["insomnio"]
    assert _derived_safety_context(_encuesta(horas_sueno="menos_5h")) == ["insomnio"]


def test_derived_insomnia_does_not_change_safety_level_but_warns() -> None:
    encuesta = _encuesta(sleep_quality="mala")
    assert _safety_level(encuesta) == "normal"
    assert any("sueño insuficiente" in w.lower() for w in _profile_warnings(encuesta))
