"""Fase 3: el score del Modelo 1 (sintetico) se expone como indice de riesgo basado en reglas, no probabilidad."""

from __future__ import annotations

from app.domains.recommendations.esquemas import (
    RULE_RISK_INDEX_LABEL,
    CategorizedConditionResult,
    ConditionDisplay,
    ConditionExplanation,
    RecommendationResponse,
)
from app.domains.recommendations.servicio_recomendaciones import (
    _categorized_condition_results,
    _normalize_conditions_display,
)


def test_schema_mirrors_probability_into_risk_index_with_rule_semantics() -> None:
    result = CategorizedConditionResult(code="DEFICIT_VIT_D", display_name="Vitamina D", kind="nutrition_risk", probability=0.62, level="alto", explanation="x")
    assert result.risk_index == 0.62
    assert result.score_semantics == "indice_riesgo_reglas"
    assert result.score_label == RULE_RISK_INDEX_LABEL
    display = ConditionDisplay(code="DEFICIT_VIT_D", display_name="Vitamina D", level="alto", probability=0.62, icon_key="activity")
    assert display.risk_index == 0.62 and display.score_semantics == "indice_riesgo_reglas"
    explanation = ConditionExplanation(condition="DEFICIT_VIT_D", probability=0.62, drivers=[])
    assert explanation.risk_index == 0.62


def test_service_populates_risk_index_for_every_condition_block() -> None:
    results, wellness, safety = _categorized_condition_results(["DEFICIT_VIT_D", "ESTRES_SUENO", "SAFETY_RENAL"], {"DEFICIT_VIT_D": 0.7, "ESTRES_SUENO": 0.6, "SAFETY_RENAL": 0.9})
    for item in results + wellness + safety:
        assert item["risk_index"] == item["probability"]
        assert item["score_semantics"] == "indice_riesgo_reglas"
    for item in _normalize_conditions_display(["DEFICIT_VIT_D"], {"DEFICIT_VIT_D": 0.7}):
        assert item["risk_index"] == 0.7 and item["score_semantics"] == "indice_riesgo_reglas"


def test_response_declares_how_to_read_condition_scores() -> None:
    fields = RecommendationResponse.model_fields
    assert fields["condition_score_semantics"].default == "indice_riesgo_reglas"
    assert fields["condition_score_label"].default == RULE_RISK_INDEX_LABEL
