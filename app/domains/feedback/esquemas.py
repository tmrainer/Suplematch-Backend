from typing import Literal

from pydantic import BaseModel, Field

from app.domains.feedback.recompensa import PerceivedBenefit

RecommendationEventType = Literal[
    "impression",
    "click",
    "product_click",
    "purchase_intent",
    "dismiss",
    "still_taking_30d",
    "stopped",
]

MAX_EVENTS_PER_BATCH = 50


class FeedbackInput(BaseModel):
    recommendation_id: str
    pack_id: str | None = None
    component_ids: list[str] = Field(default_factory=list)
    selected_product_ids: list[str] = Field(default_factory=list)
    chosen_product_id: str | None = None
    product_context: dict = Field(default_factory=dict)
    rating: int = Field(ge=1, le=5)
    conditions: list[str] = Field(default_factory=list)
    comment: str | None = None
    # Outcomes opcionales que alimentan la recompensa (ver app/domains/feedback/recompensa.py).
    purchased: bool | None = None
    still_taking_30d: bool | None = None
    perceived_benefit: PerceivedBenefit | None = None


class RecommendationEventInput(BaseModel):
    """Un evento de interaccion con una recomendacion mostrada (impresion, click, compra, etc.)."""

    recommendation_id: str = Field(min_length=1, max_length=120)
    event_type: RecommendationEventType
    pack_key: str | None = Field(default=None, max_length=160)
    component_id: str | None = Field(default=None, max_length=120)
    product_id: str | None = Field(default=None, max_length=64)
    position: int | None = Field(default=None, ge=0, le=1000, description="Rank mostrado (1 = primero).")
    conditions: list[str] = Field(default_factory=list, max_length=20)
    payload: dict = Field(default_factory=dict)


class RecommendationEventsBatch(BaseModel):
    events: list[RecommendationEventInput] = Field(min_length=1, max_length=MAX_EVENTS_PER_BATCH)
    anonymous_session_id: str | None = Field(default=None, max_length=120)


class RecommendationEventsResult(BaseModel):
    status: str
    accepted: int
    deduplicated: int
    event_ids: list[str] = Field(default_factory=list)
    detail: str | None = None
