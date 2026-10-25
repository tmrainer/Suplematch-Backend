"""Medicion de precision real: verdad desde el examen, confusion por variante e intervalos."""

from __future__ import annotations

import pytest

from app.ml.evaluation.precision_real import (
    MIN_CASES_FOR_METRIC,
    Confusion,
    build_report,
    lab_truth,
    predicted_conditions,
    wilson_interval,
)


def test_truth_follows_the_direction_of_each_condition() -> None:
    # Vitamina D alta no confirma un deficit; HDL bajo si confirma dislipidemia; TSH sirve en ambos sentidos.
    assert lab_truth({"vitamin_d": "high"}) == {"DEFICIT_VIT_D": False}
    assert lab_truth({"vitamin_d": "critical_low"}) == {"DEFICIT_VIT_D": True}
    assert lab_truth({"hdl": "low", "ldl": "normal"}) == {"RIESGO_DISLIPIDEMIA": True}
    assert lab_truth({"tsh": "high"}) == {"SAFETY_TIROIDEA": True}
    assert lab_truth({"tsh": "low"}) == {"SAFETY_TIROIDEA": True}


def test_borderline_is_not_a_deficit_and_unmeasured_conditions_are_not_evaluated() -> None:
    assert lab_truth({"vitamin_d": "borderline"}) == {"DEFICIT_VIT_D": False}
    # Hierro: basta ferritina o hemoglobina; sin examen relacionado, la condicion no entra.
    assert lab_truth({"hemoglobin": "low"}) == {"DEFICIT_HIERRO": True}
    assert lab_truth({"crp": "high"}) == {}


def test_rules_variant_uses_rule_score_threshold_and_corroboration() -> None:
    details = [
        {"condition": "A", "positive": True, "corroborated": True, "rule_score": 0.2, "rule_threshold": 0.55},
        {"condition": "B", "positive": False, "corroborated": True, "rule_score": 0.6, "rule_threshold": 0.55},
        {"condition": "C", "positive": False, "corroborated": False, "rule_score": 0.9, "rule_threshold": 0.55},
        {"condition": "D", "positive": True, "second_opinion_reason": "borderline", "rule_score": 0.4, "rule_threshold": 0.55},
    ]
    lab_risks = [{"condition": "DEFICIT_VIT_D", "positive": True}, {"condition": "SAFETY_HEPATICA", "positive": False}]
    predictions = predicted_conditions(details, lab_risks)
    assert predictions == {"sistema": {"A", "D"}, "reglas": {"B", "D"}, "nhanes": {"DEFICIT_VIT_D"}}


def test_wilson_interval_matches_known_values() -> None:
    assert wilson_interval(5, 10) == pytest.approx((0.2366, 0.7634), abs=1e-4)
    assert wilson_interval(0, 0) is None
    low, high = wilson_interval(0, 20)
    assert low == 0.0 and 0.15 < high < 0.17


def test_confusion_summary_and_sufficiency() -> None:
    confusion = Confusion()
    for predicted, actual in [(True, True)] * 6 + [(True, False)] * 4 + [(False, True)] * 4 + [(False, False)] * 6:
        confusion.add(predicted, actual)
    summary = confusion.summary()
    assert (summary["tp"], summary["fp"], summary["fn"], summary["tn"]) == (6, 4, 4, 6)
    assert summary["precision"] == 0.6 and summary["recall"] == 0.6 and summary["specificity"] == 0.6
    assert summary["sufficient"] is (MIN_CASES_FOR_METRIC <= 10)


def test_report_counts_prevalence_per_condition() -> None:
    pairs = [
        ("encuesta", {"vitamin_d": "low"}, {"sistema": {"DEFICIT_VIT_D"}, "reglas": set(), "nhanes": {"DEFICIT_VIT_D"}}),
        ("examen_subido", {"vitamin_d": "normal"}, {"sistema": {"DEFICIT_VIT_D"}, "reglas": set(), "nhanes": set()}),
        ("encuesta", {"crp": "high"}, {"sistema": set(), "reglas": set(), "nhanes": set()}),
    ]
    result = build_report(pairs).to_dict()
    assert result["pairs"] == 2 and result["sources"] == {"encuesta": 1, "examen_subido": 1}
    assert result["skipped"] == {"examen_sin_condicion_evaluable": 1}
    vit_d = result["conditions"]["DEFICIT_VIT_D"]
    assert vit_d["n"] == 2 and vit_d["prevalence"] == 0.5
    assert vit_d["predictors"]["sistema"]["precision"] == 0.5 and vit_d["predictors"]["sistema"]["recall"] == 1.0
    assert vit_d["predictors"]["reglas"]["precision"] is None and vit_d["predictors"]["reglas"]["recall"] == 0.0


def test_rules_variant_respects_supplement_suppression() -> None:
    details = [{"condition": "DEFICIT_VIT_D", "positive": False, "corroborated": True, "rule_score": 0.6, "rule_threshold": 0.55,
                "suppressed_by_supplement": "vitamina_d"}]
    assert predicted_conditions(details, [])["reglas"] == set()
