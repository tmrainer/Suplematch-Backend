from typing import Literal

from pydantic import BaseModel, Field, field_validator

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
MAX_ITEM_RATINGS = 20


class ItemRatingInput(BaseModel):
    """Estrellas (1-5) para un suplemento de la recomendacion. La condicion no se recibe: la pone el servidor."""

    component_id: str = Field(min_length=1, max_length=120)
    rating: int = Field(ge=1, le=5)
    purchased: bool | None = None
    still_taking_30d: bool | None = None


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
    # Opcional: calificacion por suplemento, solo de los que la persona vio (docs/propuesta_recomendacion_por_suplemento.md).
    item_ratings: list[ItemRatingInput] = Field(default_factory=list, max_length=MAX_ITEM_RATINGS)

    @field_validator("item_ratings")
    @classmethod
    def _one_rating_per_component(cls, value: list[ItemRatingInput]) -> list[ItemRatingInput]:
        ids = [item.component_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("item_ratings: un suplemento solo puede calificarse una vez por envio")
        return value


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
