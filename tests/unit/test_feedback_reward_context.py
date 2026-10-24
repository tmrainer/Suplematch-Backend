"""Funciones puras del feedback: recompensa, clave contextual y seleccion contexto vs global (sin Postgres)."""

import pytest
from pydantic import ValidationError

from app.domains.feedback.contexto import (
    FEEDBACK_PRIOR,
    bayesian_feedback_score,
    build_context_key,
    principal_conditions,
    select_feedback_stats,
)
from app.domains.feedback.esquemas import FeedbackInput
from app.domains.feedback.recompensa import normalize_rating, outcome_payload, reward


# --------------------------------------------------------------------------- reward
@pytest.mark.parametrize("rating,expected", [(1, 0.0), (2, 0.25), (3, 0.5), (4, 0.75), (5, 1.0)])
def test_reward_with_rating_only_is_normalized_rating(rating, expected):
    assert reward({"rating": rating}) == pytest.approx(expected)
    assert normalize_rating(rating) == pytest.approx(expected)


def test_reward_full_positive_outcomes_reaches_one():
    full = {"rating": 5, "purchased": True, "still_taking_30d": True, "perceived_benefit": "claro"}
    assert reward(full) == pytest.approx(1.0)


def test_reward_weights_match_documented_formula():
    base = {"rating": 3}  # 0.5 normalizado
    assert reward({**base, "purchased": True}) == pytest.approx(0.4 * 0.5 + 0.2)
    assert reward({**base, "still_taking_30d": True}) == pytest.approx(0.4 * 0.5 + 0.3)
    assert reward({**base, "perceived_benefit": "claro"}) == pytest.approx(0.4 * 0.5 + 0.1)
    assert reward({**base, "perceived_benefit": "leve"}) == pytest.approx(0.4 * 0.5 + 0.05)
    assert reward({**base, "perceived_benefit": "ninguno"}) == pytest.approx(0.4 * 0.5)


def test_reward_negative_outcome_does_not_subtract_but_dilutes_rating():
    # Una vez que se informa un outcome, el rating pesa 0.4: 5 estrellas sin compra = 0.4.
    assert reward({"rating": 5, "purchased": False}) == pytest.approx(0.4)
    assert reward({"rating": 1, "purchased": False, "still_taking_30d": False}) == pytest.approx(0.0)


def test_reward_accepts_pydantic_input_and_clamps():
    data = FeedbackInput(recommendation_id="rec_1", rating=5, purchased=True, still_taking_30d=True, perceived_benefit="claro")
    assert 0.0 <= reward(data) <= 1.0
    payload = outcome_payload(data)
    assert payload["purchased"] is True
    assert payload["still_taking_30d"] is True
    assert payload["perceived_benefit"] == "claro"
    assert payload["reward"] == pytest.approx(1.0)
    assert payload["reward_version"] == "v1"


def test_feedback_input_rejects_unknown_perceived_benefit():
    with pytest.raises(ValidationError):
        FeedbackInput(recommendation_id="rec_1", rating=4, perceived_benefit="enorme")


def test_feedback_input_outcomes_default_to_none_for_backwards_compatibility():
    data = FeedbackInput(recommendation_id="rec_1", rating=4)
    assert data.purchased is None and data.still_taking_30d is None and data.perceived_benefit is None
    assert outcome_payload(data)["reward"] == pytest.approx(0.75)


# --------------------------------------------------------------------------- context key
def test_principal_conditions_excludes_healthy_dedupes_and_sorts_first_three():
    conditions = ["ESTRES_CRONICO", "SALUDABLE", "DEFICIT_VIT_D", "DEFICIT_VIT_D", "BAJO_INMUNE", "DEFICIT_HIERRO"]
    # Las 3 primeras utiles por orden de confianza (sin SALUDABLE ni duplicados), luego ordenadas.
    assert principal_conditions(conditions) == ["BAJO_INMUNE", "DEFICIT_VIT_D", "ESTRES_CRONICO"]


def test_build_context_key_is_canonical_regardless_of_order():
    key_a = build_context_key("pack_abc", ["DEFICIT_VIT_D", "ESTRES_CRONICO"])
    key_b = build_context_key("pack_abc", ["ESTRES_CRONICO", "DEFICIT_VIT_D"])
    assert key_a == key_b == "pack_abc|DEFICIT_VIT_D+ESTRES_CRONICO"


def test_build_context_key_edge_cases():
    assert build_context_key(None, ["X"]) is None
    assert build_context_key("", ["X"]) is None
    assert build_context_key("pack_1", []) == "pack_1|"
    assert build_context_key("pack_1", ["SALUDABLE"]) == "pack_1|"
    assert build_context_key("pack_1", None) == "pack_1|"


# --------------------------------------------------------------------------- bayes + seleccion
def test_bayesian_score_shrinks_towards_prior_with_few_votes():
    assert bayesian_feedback_score(None, 0) == pytest.approx(FEEDBACK_PRIOR)
    one_vote = bayesian_feedback_score(1.0, 1)
    many_votes = bayesian_feedback_score(1.0, 50)
    assert FEEDBACK_PRIOR < one_vote < many_votes < 1.0


def test_select_feedback_stats_prefers_context_when_enough_votes():
    result = select_feedback_stats((0.9, 3), (0.2, 40))
    assert result["source"] == "context"
    assert result["feedback_count"] == 3
    assert result["feedback_context_count"] == 3
    assert result["feedback_global_count"] == 40
    assert result["score"] > FEEDBACK_PRIOR


def test_select_feedback_stats_falls_back_to_global_when_context_too_small():
    result = select_feedback_stats((0.9, 2), (0.2, 40))
    assert result["source"] == "global"
    assert result["feedback_count"] == 40
    assert result["feedback_context_count"] == 2
    assert result["score"] < FEEDBACK_PRIOR


def test_select_feedback_stats_without_data_returns_prior():
    result = select_feedback_stats(None, None)
    assert result == {
        "score": FEEDBACK_PRIOR,
        "source": "none",
        "feedback_count": 0,
        "feedback_context_count": 0,
        "feedback_global_count": 0,
    }
    assert select_feedback_stats((None, 0), (None, 0))["source"] == "none"
