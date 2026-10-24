"""Paridad entre las features que produce FeatureBuilder y las que espera el runtime de condition_mvp."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

from app.domains.survey.esquemas_encuesta import EncuestaInput
from app.ml.feature_builder import FeatureBuilder
from app.ml.features_contract import BUILDER_ONLY_KEYS, CAT_COLS, MISSING_CATEGORY, NUM_COLS, prepare_features

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "training"))


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


def _build(**overrides) -> dict:
    return FeatureBuilder().build_pipeline_payload(EncuestaInput(**_payload(**overrides)))


def test_payload_is_deterministic() -> None:
    assert _build() == _build()


def test_payload_has_core_survey_features() -> None:
    payload = _build()
    for key in ("edad", "sexo", "tipo_dieta", "problemas_sueno", "fatiga_general", "exposicion_solar"):
        assert key in payload, key


def test_numeric_features_are_finite() -> None:
    for key, value in _build().items():
        if isinstance(value, float):
            assert math.isfinite(value), key


def test_vegan_diet_lowers_b12_diet_status() -> None:
    payload = _build(tipo_dieta="vegano")
    assert payload["benchmark_diet_b12_status"] in {"low", "critical_low"}


def test_runtime_can_prepare_every_training_column_from_builder_payload() -> None:
    entrenar = pytest.importorskip("entrenar_modelo_condiciones")
    cat_cols, num_cols = entrenar.CAT_COLS, entrenar.NUM_COLS
    # Training y runtime deben compartir la misma definicion (app/ml/features_contract.py).
    assert cat_cols == CAT_COLS and num_cols == NUM_COLS

    prepared = prepare_features(_build(), cat_cols, num_cols)

    missing = [col for col in cat_cols + num_cols if col not in prepared]
    assert not missing, missing
    for col in num_cols:
        assert isinstance(prepared[col], (int, float)), col
        assert math.isfinite(float(prepared[col])), col
    for col in cat_cols:
        assert isinstance(prepared[col], str), col


def test_builder_payload_has_no_undeclared_model_features() -> None:
    """Toda clave del payload es feature del contrato o esta documentada en BUILDER_ONLY_KEYS."""
    payload = _build(tipo_dieta="vegano", sexo="masculino")
    undeclared = set(payload) - set(CAT_COLS) - set(NUM_COLS) - BUILDER_ONLY_KEYS
    assert not undeclared, sorted(undeclared)


def test_builder_payload_never_emits_unknown_category() -> None:
    for overrides in ({}, {"tipo_dieta": "vegetariano"}, {"sexo": "masculino", "edad_rango": "mas_50"}):
        payload = _build(**overrides)
        for col in CAT_COLS:
            value = payload.get(col, MISSING_CATEGORY)
            assert isinstance(value, str) and value != "unknown", (col, value)
