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
    selected_products: list["HistorySelectedProductOut"] = Field(default_factory=list)


class HistoryRecommendationItemOut(BaseModel):
    id: UUID
    component_id: str | None = None
    component_name: str | None = None
    rank: int
    reason: str | None = None
    score_model: float | None = None
    recommendation_type: str | None = None
    condition_code: str | None = None


class HistorySelectedProductOut(BaseModel):
    component_id: str | None = None
    component_name: str | None = None
    product_id: UUID | None = None
    commercial_name: str | None = None
    pharmacy: str | None = None
    url: str | None = None
    price_at_recommendation: float | None = None
    availability_at_recommendation: str | None = None
    product_score: float | None = None
    review_score: float | None = None
    price_score: float | None = None
    stock_score: float | None = None
    traceability_score: float | None = None
    pharmacy_diversity_score: float | None = None
    selection_metrics: dict = Field(default_factory=dict)


class RecommendationHistoryOut(BaseModel):
    id: UUID
    recommendation_id: str | None
    created_at: datetime
    conditions: list[str] = Field(default_factory=list)
    profile_warnings: list[str] = Field(default_factory=list)
    items: list[HistoryRecommendationItemOut] = Field(default_factory=list)
    packs: list[HistoryPackOut] = Field(default_factory=list)
