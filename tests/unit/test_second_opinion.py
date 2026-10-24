"""Segunda opinion del modelo real (NHANES) para condiciones limitrofes."""

from __future__ import annotations

from app.ml.runtime.condition_mvp_inference import (
    SECOND_OPINION_MARGIN,
    apply_second_opinion,
    second_opinion_from_lab_risks,
)


def _detail(**overrides) -> dict:
    data = {
        "condition": "DEFICIT_VIT_D",
        "probability": 0.12,
        "positive": False,
        "corroborated": True,
        "rule_score": 0.52,
        "rule_threshold": 0.55,
        "threshold": 0.44,
        "score_basis": "model",
    }
    data.update(overrides)
    return data


def test_only_enabled_positive_targets_become_second_opinion() -> None:
    risks = [
        {"target": "target_vitamin_d_low", "probability": 0.47, "positive": True},
        {"target": "target_ferritin_low", "probability": 0.60, "positive": True},  # AUC 0.58: no habilitado
        {"target": "target_glucose_high", "probability": 0.10, "positive": False},
    ]
    assert second_opinion_from_lab_risks(risks) == {"DEFICIT_VIT_D": 0.47}
    assert second_opinion_from_lab_risks([{"target": "target_vitamin_d_low", "probability": 0.2, "positive": False}]) == {}


def test_borderline_corroborated_condition_is_marked_with_real_probability() -> None:
    [item] = apply_second_opinion([_detail()], {"DEFICIT_VIT_D": 0.47})
    assert item["positive"] is True
    assert item["probability"] == 0.47
    assert item["score_basis"] == "rules+second_opinion_nhanes"


def test_real_model_never_marks_alone() -> None:
    # Sin confirmacion de la encuesta (una sola familia, p. ej. solo poco sol).
    assert apply_second_opinion([_detail(corroborated=False)], {"DEFICIT_VIT_D": 0.6})[0]["positive"] is False
    # Reglas lejos del umbral.
    far = _detail(rule_score=0.55 - SECOND_OPINION_MARGIN - 0.01)
    assert apply_second_opinion([far], {"DEFICIT_VIT_D": 0.6})[0]["positive"] is False
    # Sin estimacion positiva del modelo real.
    assert apply_second_opinion([_detail()], {})[0]["positive"] is False


def test_already_positive_conditions_are_untouched() -> None:
    detail = _detail(positive=True, probability=0.8)
    assert apply_second_opinion([detail], {"DEFICIT_VIT_D": 0.4})[0] == detail
