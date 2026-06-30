from __future__ import annotations

from datetime import datetime
from uuid import UUID

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProductReviewCreate(BaseModel):
    product_id: UUID
    rating: int = Field(ge=1, le=5)
    effectiveness_score: int | None = Field(default=None, ge=1, le=5)
    side_effects_score: int | None = Field(default=None, ge=1, le=5)
    price_value_score: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)
    source: Literal["detailed", "quick_recommendation"] = "detailed"


class SupplementReviewCreate(ProductReviewCreate):
    # Compatibilidad legacy: el componente ya no lo decide el usuario.
    # Si llega desde un cliente antiguo, el repositorio lo ignora y deriva el
    # componente principal desde el producto comercial.
    component_id: UUID | None = None


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


class SupplementReviewModerationOut(SupplementReviewOut):
    product_name: str | None = None
    pharmacy: str | None = None
    component_name: str | None = None
    spam_flags: list[str] = Field(default_factory=list)


ProductReviewOut = SupplementReviewOut
ProductReviewModerationOut = SupplementReviewModerationOut
