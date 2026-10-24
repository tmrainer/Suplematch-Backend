"""Garantias anti-fuga del entrenamiento con datos reales (NHANES)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

nhanes = pytest.importorskip("scripts.training.entrenar_condiciones_nhanes")


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "SEQN": [1, 2, 3, 4],
            "RIAGENDR": [1, 2, 2, 1],
            "RIDAGEYR": [30, 40, 55, 70],
            "BMXBMI": [22.0, 31.0, np.nan, 27.0],
            "LBXVIDMS": [40.0, 60.0, np.nan, 25.0],   # nmol/L: 16, 24, -, 10 ng/mL
            "LBXFER": [10.0, 50.0, 20.0, np.nan],
            "LBXHGB": [12.5, 11.0, 13.0, 14.0],        # hombre 12.5 = anemia; mujer 11.0 = anemia
            "LBXGLU": [90.0, 110.0, 99.0, 130.0],
            "LBXTC": [180.0, 210.0, 199.0, 250.0],
            "LBDHDD": [50.0, 35.0, 40.0, 39.0],
            "LBXSATSI": [20.0, 45.0, 40.0, 41.0],
        }
    )


def test_features_never_contain_laboratory_columns() -> None:
    features = nhanes.features_from_questionnaire(_frame())
    assert not [c for c in features.columns if c.upper().startswith(("LBX", "LBD"))]
    assert list(features.columns) == nhanes.CAT_FEATURES + nhanes.NUM_FEATURES
    assert set(features["sexo"]) == {"masculino", "femenino"}


def test_targets_use_knowledge_cutoffs_and_who_hemoglobin_by_sex() -> None:
    cutoffs = nhanes.biomarker_cutoffs()
    targets = nhanes.targets_from_labs(_frame(), cutoffs)
    assert targets["target_vitamin_d_low"].tolist()[:2] == [1.0, 0.0]  # 16 ng/mL < 20; 24 >= 20
    assert np.isnan(targets["target_vitamin_d_low"].iloc[2])
    assert targets["target_anemia"].tolist() == [1.0, 1.0, 0.0, 0.0]
    assert targets["target_glucose_high"].tolist() == [0.0, 1.0, 0.0, 1.0]
    assert targets["target_hdl_low"].tolist() == [0.0, 1.0, 0.0, 1.0]


def test_targets_tolerate_missing_lab_file() -> None:
    frame = _frame().drop(columns=["LBXFER"])
    targets = nhanes.targets_from_labs(frame, nhanes.biomarker_cutoffs())
    assert targets["target_ferritin_low"].isna().all()


def test_ferritin_population_is_women_under_50_in_both_cycles() -> None:
    features = nhanes.features_from_questionnaire(_frame())
    mask = nhanes.population_mask(features, "target_ferritin_low")
    assert mask.tolist() == [False, True, False, False]


def test_threshold_is_chosen_on_validation_and_never_below_030() -> None:
    y = np.array([0, 0, 0, 1, 1, 1, 0, 1])
    p = np.array([0.1, 0.2, 0.35, 0.4, 0.6, 0.9, 0.05, 0.5])
    threshold = nhanes.choose_threshold(y, p)
    assert 0.30 <= threshold <= 0.90


def test_ece_is_zero_for_perfectly_calibrated_bins() -> None:
    y = np.array([0, 1] * 50)
    p = np.full(100, 0.5)
    assert nhanes.expected_calibration_error(y, p) == pytest.approx(0.0, abs=1e-9)
