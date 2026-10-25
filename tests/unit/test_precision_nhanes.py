"""Mapeo NHANES 2013-2014 -> encuesta de SupleMatch (scripts/validation/precision_nhanes.py)."""

from __future__ import annotations

import math

import pytest

from app.domains.survey.esquemas_encuesta import EncuestaInput
from scripts.validation.precision_nhanes import (
    alcohol_per_week,
    exercise_days,
    lab_values,
    sleep_range,
    stress_level,
    sun_range,
    survey_from_nhanes,
)


def _row(**overrides) -> dict:
    row = {
        "RIAGENDR": 2, "RIDAGEYR": 45, "RIDEXPRG": 2, "BMXWT": 70.0, "BMXHT": 160.0,
        "DEQ034D": 1, "DED120": 10, "DED125": 30,
        "DPQ010": 0, "DPQ020": 1, "DPQ030": 3, "DPQ040": 2, "DPQ050": 0, "DPQ060": 0, "DPQ070": 1, "DPQ080": 0, "DPQ090": 0,
        "SLD010H": 6, "PAQ650": 2, "PAQ655": math.nan, "PAQ665": 1, "PAQ670": 3,
        "ALQ101": 1, "ALQ110": math.nan, "ALQ120Q": 2, "ALQ120U": 1, "ALQ130": 2,
        "SMQ020": 1, "SMQ040": 3, "HSD010": 3, "DIQ050": 2, "DIQ070": 1,
        "DSDCOUNT": 1, "DSQTVD": 25.0, "DSQTIRON": 0.0,
        "metformina": "si", "antiacidos": "no",
        "LBXVIDMS": 40.0, "LBXGH": 6.1, "LBXHGB": 13.0,
    }
    row.update(overrides)
    return row


def test_answer_ranges() -> None:
    assert [sleep_range(h) for h in (4, 5, 6.5, 7, 9, 99)] == ["menos_5h", "5_7h", "5_7h", "7_9h", "mas_9h", None]
    assert sun_range(10, 30) == "15_30min"  # (5*10 + 2*30) / 7 = 15.7
    assert sun_range(None, 120) == "mas_1h" and sun_range(None, None) is None
    assert stress_level([0, 0, 0, 0, 0, 0, 3]) == "bajo" and stress_level([3, 3, 3, 3, 0, 0, 0]) == "muy_alto"
    assert stress_level([0, None, 0, 0, 0, 0, 0]) is None


def test_alcohol_and_exercise() -> None:
    assert alcohol_per_week({"ALQ101": 2, "ALQ110": 2}) == 0.0
    assert alcohol_per_week({"ALQ101": 1, "ALQ120Q": 0}) == 0.0
    assert alcohol_per_week({"ALQ101": 1, "ALQ120Q": 2, "ALQ120U": 1, "ALQ130": 3}) == 6.0
    assert alcohol_per_week({"ALQ101": 1, "ALQ120Q": 999}) is None
    assert exercise_days({"PAQ650": 1, "PAQ655": 5, "PAQ665": 1, "PAQ670": 2}) == 5
    assert exercise_days({"PAQ650": 2, "PAQ665": 2}) == 0
    assert exercise_days({"PAQ650": 9, "PAQ665": 2}) is None


def test_row_becomes_a_valid_survey() -> None:
    survey, reason = survey_from_nhanes(_row())
    assert reason is None
    encuesta = EncuestaInput(**survey)
    assert encuesta.fatiga == "a_menudo" and encuesta.horas_sueno == "5_7h" and encuesta.exposicion_solar == "15_30min"
    assert encuesta.estres == "bajo"  # sin los items de sueño (3) y fatiga (2): 0+1+0+0+1+0+0
    assert encuesta.frecuencia_ejercicio == "3_4_semana" and encuesta.alcohol == "ocasional"
    assert encuesta.tabaco == "ex" and encuesta.salud_autopercibida == "buena" and encuesta.protector_solar == "siempre"
    assert encuesta.condiciones_seguridad == ["diabetes_medicada"] and encuesta.medicamentos_b12 == ["metformina"]
    assert encuesta.suplementos_actuales == ["vitamina_d"]
    assert encuesta.suplementos_dosis_actual["vitamina_d"].amount == 25.0


def test_missing_required_answer_skips_the_row() -> None:
    assert survey_from_nhanes(_row(DPQ040=9)) == (None, "falta_fatiga")
    survey, _ = survey_from_nhanes(_row(DSQTVD=0.0))
    assert survey["suplementos_actuales"] == ["otro"]


def test_labs_are_converted_to_biomarker_units() -> None:
    values = {item.code: (item.value, item.unit) for item in lab_values(_row())}
    assert values["vitamin_d"] == (pytest.approx(16.0), "ng/mL")  # 40 nmol/L
    assert values["hba1c"] == (6.1, "%") and values["hemoglobin"] == (13.0, "g/dL")
    assert "b12" not in values
