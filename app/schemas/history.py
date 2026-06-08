from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class HistoryPackOut(BaseModel):
    id: UUID
    pack_key: str
    rank: int
    score_final: float | None
    score_gnn: float | None
    score_feedback: float | None
    score_reviews: float | None = None
    score_exposure: float | None = None
    score_products: float | None = None
    score_diversity: float | None = None
    component_ids: list[str] = Field(default_factory=list)
    component_names: list[str] = Field(default_factory=list)


class RecommendationHistoryOut(BaseModel):
    id: UUID
    recommendation_id: str | None
    created_at: datetime
    conditions: list[str] = Field(default_factory=list)
    packs: list[HistoryPackOut] = Field(default_factory=list)
