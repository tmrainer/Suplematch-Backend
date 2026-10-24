"""Test de paridad estricto del contrato de features compartido (training == runtime == FeatureBuilder).

Ver docs/plan_fiabilidad.md Fase 3 y docs/condition_mvp_pipeline.md ("Contrato de features compartido").
"""

from __future__ import annotations

import csv
import logging
import math
import random
import re
import sys
from pathlib import Path

import pytest

from app.core.config import settings
from app.domains.survey.esquemas_encuesta import EncuestaInput
from app.ml import features_contract as fc
from app.ml.feature_builder import FeatureBuilder

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "training"))

MODEL_PATH = Path(settings.MODEL_DIR) / "condition_mvp_model.pkl"
CONTRACT = set(fc.CAT_COLS + fc.NUM_COLS)


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


_SURVEY_VARIANTS = [
    {},
    {"tipo_dieta": "vegano", "sexo": "masculino", "edad_rango": "mas_50"},
    {"tipo_dieta": "vegetariano", "fatiga": "siempre", "estres": "muy_alto", "horas_sueno": "menos_5h"},
    {"frecuencia_ejercicio": "diario", "dieta": "poco_variada", "exposicion_solar": "mas_1h"},
]


# ---------------------------------------------------------------------------------------------
# Integridad del contrato
# ---------------------------------------------------------------------------------------------

def test_contract_version_is_a_date_string() -> None:
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}(\.\d+)?", fc.FEATURE_CONTRACT_VERSION)


def test_contract_columns_have_no_duplicates_or_overlap() -> None:
    assert len(fc.CAT_COLS) == len(set(fc.CAT_COLS))
    assert len(fc.NUM_COLS) == len(set(fc.NUM_COLS))
    assert not set(fc.CAT_COLS) & set(fc.NUM_COLS)
    assert fc.MODEL_FEATURE_COLS == fc.CAT_COLS + fc.NUM_COLS


def test_contract_resolves_known_training_runtime_divergences() -> None:
    # Gana la version del runtime: 12 sintomas, 8 cantidades de dieta, 10 senales blandas.
    assert len(fc.SYMPTOM_COLS) == 12 and "digestive_discomfort" in fc.SYMPTOM_COLS
    assert len(fc.DIET_QUANTITY_COLS) == 8
    assert {"fermented_foods_week", "water_intake_l_day"} <= set(fc.DIET_QUANTITY_COLS)
    assert len(fc.SOFT_SIGNAL_COLS) == 10
    assert fc.MISSING_CATEGORY == "missing"
    for group in (fc.SYMPTOM_COLS, fc.DIET_QUANTITY_COLS, fc.DIET_META_COLS, fc.SOFT_SIGNAL_COLS, fc.LAB_META_COLS):
        assert set(group) <= set(fc.NUM_COLS)
    assert set(fc.LAB_STATUS_COLS) | set(fc.BENCHMARK_STATUS_COLS) <= set(fc.CAT_COLS)
    assert fc.MEDICAL_SAFETY_COLS <= set(fc.LAB_STATUS_COLS)


def test_hair_skin_nails_cluster_excludes_diet_zinc_proxy() -> None:
    base = {"meta_belleza": 1, "caida_cabello": 5, "piel_seca": 5, "unas_quebradizas": 1}
    with_diet_zinc = {**base, "benchmark_diet_zinc_status": "low"}
    with_lab_zinc = {**base, "lab_zinc_status": "low"}
    fc.attach_soft_signal_features(base)
    fc.attach_soft_signal_features(with_diet_zinc)
    fc.attach_soft_signal_features(with_lab_zinc)
    assert base["hair_skin_nails_cluster"] == 3
    assert with_diet_zinc["hair_skin_nails_cluster"] == 3
    assert with_lab_zinc["hair_skin_nails_cluster"] == 4


def test_rule_matches_ignores_negative_sentinels_and_rejects_unknown_operator() -> None:
    assert not fc.rule_matches({"fish_servings_week": -1.0}, {"field": "fish_servings_week", "operator": "lte", "value": 1})
    assert fc.rule_matches({"fish_servings_week": 0.5}, {"field": "fish_servings_week", "operator": "lte", "value": 1})
    assert fc.rule_matches({"lab_b12_status": "low"}, {"field": "lab_b12_status", "operator": "in", "value": ["low", "critical_low"]})
    assert not fc.rule_matches({}, {"field": "edad", "operator": "gte", "value": 50})
    with pytest.raises(ValueError):
        fc.rule_matches({"edad": 3}, {"field": "edad", "operator": "between", "value": 1})


def test_condition_rules_only_reference_contract_features() -> None:
    with (ROOT / "data/knowledge/condition_rules.csv").open(encoding="utf-8", newline="") as handle:
        fields = {row["field"] for row in csv.DictReader(handle)}
    assert fields <= CONTRACT, sorted(fields - CONTRACT)


# ---------------------------------------------------------------------------------------------
# (a) + (b): FeatureBuilder -> prepare_features produce exactamente el contrato
# ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("overrides", _SURVEY_VARIANTS)
def test_builder_payload_extras_are_exactly_the_documented_set(overrides: dict) -> None:
    payload = FeatureBuilder().build_pipeline_payload(_encuesta(**overrides))
    extras = set(payload) - CONTRACT
    assert extras == set(fc.BUILDER_ONLY_KEYS), {
        "undocumented": sorted(extras - fc.BUILDER_ONLY_KEYS),
        "documented_but_absent": sorted(fc.BUILDER_ONLY_KEYS - extras),
    }
    # Toda clave del builder que SI esta en el contrato debe ser una feature real del modelo.
    assert (set(payload) - fc.BUILDER_ONLY_KEYS) <= CONTRACT


@pytest.mark.parametrize("overrides", _SURVEY_VARIANTS)
def test_prepare_features_from_builder_yields_full_contract_without_silent_extras(overrides: dict) -> None:
    payload = FeatureBuilder().build_pipeline_payload(_encuesta(**overrides))
    prepared = fc.prepare_features(payload, fc.CAT_COLS, fc.NUM_COLS)

    missing = [col for col in fc.MODEL_FEATURE_COLS if col not in prepared]
    assert not missing, missing
    extras = set(prepared) - CONTRACT
    assert extras == set(fc.BUILDER_ONLY_KEYS), sorted(extras ^ fc.BUILDER_ONLY_KEYS)

    for col in fc.NUM_COLS:
        assert isinstance(prepared[col], (int, float)) and not isinstance(prepared[col], bool), col
        assert math.isfinite(float(prepared[col])), col
    for col in fc.CAT_COLS:
        assert isinstance(prepared[col], str) and prepared[col], col


@pytest.mark.parametrize("overrides", _SURVEY_VARIANTS)
def test_no_categorical_feature_is_unknown(overrides: dict) -> None:
    payload = FeatureBuilder().build_pipeline_payload(_encuesta(**overrides))
    prepared = fc.prepare_features(payload, fc.CAT_COLS, fc.NUM_COLS)
    assert all(prepared[col] != "unknown" for col in fc.CAT_COLS)
    assert all(payload.get(col) != "unknown" for col in fc.CAT_COLS)


def test_prepare_features_fills_none_categoricals_with_missing_category() -> None:
    prepared = fc.prepare_features({"sexo": None, "lab_b12_status": None}, fc.CAT_COLS, fc.NUM_COLS)
    assert prepared["sexo"] == fc.MISSING_CATEGORY
    assert prepared["lab_b12_status"] == fc.MISSING_CATEGORY
    assert prepared["lab_b12_observed"] == 0


# ---------------------------------------------------------------------------------------------
# (c): el artefacto entrenado coincide con el contrato
# ---------------------------------------------------------------------------------------------

@pytest.mark.skipif(not MODEL_PATH.exists(), reason="condition_mvp_model.pkl no esta en MODEL_DIR (no versionado)")
def test_trained_artifact_matches_contract() -> None:
    import joblib

    artifact = joblib.load(MODEL_PATH)
    assert list(artifact["cat_cols"]) == fc.CAT_COLS
    assert list(artifact["num_cols"]) == fc.NUM_COLS
    assert artifact.get("feature_contract_version") == fc.FEATURE_CONTRACT_VERSION


def test_runtime_warns_on_contract_version_drift(caplog: pytest.LogCaptureFixture) -> None:
    from app.ml.runtime import condition_mvp_inference as runtime

    current = {"feature_contract_version": fc.FEATURE_CONTRACT_VERSION, "cat_cols": fc.CAT_COLS, "num_cols": fc.NUM_COLS}
    stale = {**current, "feature_contract_version": "2000-01-01.0"}

    with caplog.at_level(logging.WARNING, logger=runtime.__name__):
        runtime._warn_on_contract_drift(current, MODEL_PATH)
        assert not caplog.records
        runtime._warn_on_contract_drift(stale, MODEL_PATH)
    assert any("feature_contract_version" in record.getMessage() for record in caplog.records)


# ---------------------------------------------------------------------------------------------
# (d): el generador de entrenamiento produce exactamente las columnas del contrato
# ---------------------------------------------------------------------------------------------

def test_training_module_reuses_contract_objects() -> None:
    entrenar = pytest.importorskip("entrenar_modelo_condiciones")
    assert entrenar.CAT_COLS is fc.CAT_COLS
    assert entrenar.NUM_COLS is fc.NUM_COLS
    assert entrenar.SYMPTOM_COLS is fc.SYMPTOM_COLS
    assert entrenar.DIET_QUANTITY_COLS is fc.DIET_QUANTITY_COLS
    assert entrenar.SOFT_SIGNAL_COLS is fc.SOFT_SIGNAL_COLS
    assert entrenar.rule_matches is fc.rule_matches
    assert entrenar.attach_soft_signal_features is fc.attach_soft_signal_features


def test_synthetic_row_columns_equal_contract_exactly() -> None:
    entrenar = pytest.importorskip("entrenar_modelo_condiciones")
    rng = random.Random(7)
    for _ in range(50):
        row = entrenar.build_synthetic_row(rng)
        assert set(row) == CONTRACT, {"missing": sorted(CONTRACT - set(row)), "extra": sorted(set(row) - CONTRACT)}
        for col in fc.CAT_COLS:
            assert isinstance(row[col], str) and row[col] != "unknown", col
        for col in fc.NUM_COLS:
            assert math.isfinite(float(row[col])), col


def test_generate_dataset_columns_are_contract_plus_targets() -> None:
    entrenar = pytest.importorskip("entrenar_modelo_condiciones")
    knowledge = entrenar.load_knowledge()
    df = entrenar.generate_dataset(knowledge, n_rows=40, seed=3)
    labels = knowledge["conditions"]["labels"]
    expected_extra = {f"{prefix}_{label}" for label in labels for prefix in ("target", "rule_score", "evidence")}
    assert set(df.columns) == CONTRACT | expected_extra
    assert not df[fc.MODEL_FEATURE_COLS].isna().any().any()


def test_runtime_derivations_reproduce_training_derivations() -> None:
    """Paridad estricta: la misma fila cruda produce las mismas features derivadas en training y runtime."""
    entrenar = pytest.importorskip("entrenar_modelo_condiciones")
    deterministic_derived = (
        set(fc.SOFT_SIGNAL_COLS)
        | set(fc.SYMPTOM_AGGREGATE_COLS)
        | set(fc.DIET_META_COLS)
        | set(fc.LAB_COUNT_COLS)
        | {f"lab_{base}_observed" for base in fc.LAB_BASES}
    )
    # age_days/unit_known/range_known son aleatorios en el dataset sintetico y no se comparan.
    rng = random.Random(11)
    for _ in range(100):
        training_row = entrenar.build_synthetic_row(rng)
        raw = {key: value for key, value in training_row.items() if key not in deterministic_derived}
        raw = {key: value for key, value in raw.items() if not key.startswith("lab_") or key.endswith("_status") or key == "lab_panel_source"}
        prepared = fc.prepare_features(raw, fc.CAT_COLS, fc.NUM_COLS)
        for col in sorted(deterministic_derived):
            assert prepared[col] == training_row[col], (col, prepared[col], training_row[col])
