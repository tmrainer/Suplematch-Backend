from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SupplementReviewCreate(BaseModel):
    product_id: UUID
    component_id: UUID | None = None
    rating: int = Field(ge=1, le=5)
    effectiveness_score: int | None = Field(default=None, ge=1, le=5)
    side_effects_score: int | None = Field(default=None, ge=1, le=5)
    price_value_score: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


class ReviewModerationInput(BaseModel):
    status: str = Field(pattern="^(published|pending|hidden|rejected)$")


class SupplementReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID | None
    product_id: UUID
    component_id: UUID | None
    rating: int
    effectiveness_score: int | None
    side_effects_score: int | None
    price_value_score: int | None
    comment: str | None
    verified_purchase: bool
    status: str
    created_at: datetime
