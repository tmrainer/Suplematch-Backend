"""Calificacion por suplemento: el feedback ordena dentro del mismo nivel, nunca por encima."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domains.feedback.calificacion_suplementos import rerank_within_tiers, user_rating
from app.domains.feedback.contexto import FEEDBACK_PRIOR, MIN_ITEM_FEEDBACK_TO_RERANK, build_item_context_key
from app.domains.feedback.esquemas import FeedbackInput


def _item(component_id: str, *, priority: str = "complementaria", grade: str = "moderate", blocked: bool = False, score: float | None = None) -> dict:
    item = {
        "component_id": component_id,
        "condition": "DEFICIT_VIT_D",
        "priority": priority,
        "evidence_grade": grade,
        "commercial_recommendation_blocked": blocked,
    }
    if score is not None:
        item["user_rating"] = {"score": score}
    return item


def _ids(items: list[dict]) -> list[str]:
    return [item["component_id"] for item in items]


def test_feedback_reorders_only_inside_the_same_tier() -> None:
    items = [
        _item("principal", priority="principal", score=0.10),
        _item("comp_a", score=0.40),
        _item("comp_b", score=0.95),
    ]
    assert _ids(rerank_within_tiers(items)) == ["principal", "comp_b", "comp_a"]


def test_feedback_never_beats_stronger_evidence_or_a_commercial_block() -> None:
    items = [
        _item("fuerte", grade="high", score=0.20),
        _item("debil", grade="low", score=0.99),
        _item("bloqueado", blocked=True, score=0.99),
        _item("libre", score=0.10),
    ]
    assert _ids(rerank_within_tiers(items)) == ["fuerte", "debil", "bloqueado", "libre"]


def test_without_votes_the_model_order_is_kept() -> None:
    items = [_item(name) for name in ("a", "b", "c")]
    assert _ids(rerank_within_tiers(items)) == ["a", "b", "c"]


def test_stars_are_hidden_until_enough_votes() -> None:
    item = _item("cmp")
    key = build_item_context_key("cmp", "DEFICIT_VIT_D")
    few = user_rating(item, {key: (0.0, 1.0, MIN_ITEM_FEEDBACK_TO_RERANK - 1)}, {"cmp": (0.0, 1.0, MIN_ITEM_FEEDBACK_TO_RERANK - 1)})
    assert few["stars"] is None and few["score"] == FEEDBACK_PRIOR and few["source"] == "insufficient"

    enough = user_rating(item, {key: (0.0, 1.0, MIN_ITEM_FEEDBACK_TO_RERANK)}, {"cmp": (0.0, 1.0, MIN_ITEM_FEEDBACK_TO_RERANK)})
    assert enough["stars"] == 1.0 and enough["count"] == MIN_ITEM_FEEDBACK_TO_RERANK
    assert enough["source"] == "context" and enough["score"] < FEEDBACK_PRIOR


def test_other_conditions_count_when_this_one_has_few_votes() -> None:
    item = _item("cmp")
    key = build_item_context_key("cmp", "DEFICIT_VIT_D")
    result = user_rating(item, {key: (1.0, 5.0, 2)}, {"cmp": (1.0, 4.6, 15)})
    assert result["source"] == "global" and result["stars"] == 4.6 and result["count"] == 15


def test_a_supplement_is_rated_once_per_submission() -> None:
    base = {"recommendation_id": "rec_x", "rating": 5}
    FeedbackInput(**base, item_ratings=[{"component_id": "a", "rating": 4}, {"component_id": "b", "rating": 2}])
    with pytest.raises(ValidationError):
        FeedbackInput(**base, item_ratings=[{"component_id": "a", "rating": 4}, {"component_id": "a", "rating": 2}])
    with pytest.raises(ValidationError):
        FeedbackInput(**base, item_ratings=[{"component_id": "a", "rating": 6}])
