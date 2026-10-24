"""Smoke del Modelo 1 (condition_mvp). Se omite si el artefacto no esta en MODEL_DIR."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from app.core.config import settings
from app.domains.survey.esquemas_encuesta import EncuestaInput
from app.ml.feature_builder import FeatureBuilder
from app.ml.model_loader import check_model_artifacts

ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(
    not (Path(settings.MODEL_DIR) / "condition_mvp_model.pkl").exists(),
    reason="condition_mvp_model.pkl no esta en MODEL_DIR; entrenar con scripts/training/entrenar_modelo_condiciones.py",
)


def _encuesta(**overrides) -> EncuestaInput:
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
    return EncuestaInput(**data)


def test_artifact_check_reports_model1_present() -> None:
    status = check_model_artifacts()
    assert status["model1"] == "condition_mvp_model.pkl"


def test_predictions_are_probabilities_over_known_conditions() -> None:
    from app.ml.runtime.condition_mvp_inference import predict_condition_probabilities

    with (ROOT / "data/knowledge/conditions.csv").open(encoding="utf-8") as handle:
        known = {row["condition_code"] for row in csv.DictReader(handle)}

    payload = FeatureBuilder().build_pipeline_payload(_encuesta())
    details = predict_condition_probabilities(payload)

    assert details
    for item in details:
        assert item["condition"] in known, item["condition"]
        assert 0.0 <= float(item["probability"]) <= 1.0
        assert isinstance(item["positive"], bool)
        # El runtime debe exponer por separado la salida del modelo y la de las reglas.
        assert "model_probability" in item
        assert "rule_score" in item


def test_no_labs_profile_does_not_flag_lab_only_conditions_as_observed() -> None:
    from app.ml.runtime.condition_mvp_inference import predict_condition_probabilities

    payload = FeatureBuilder().build_pipeline_payload(_encuesta())
    for item in predict_condition_probabilities(payload):
        if item["positive"]:
            assert item.get("primary_signal_group") != "observed_lab", item
