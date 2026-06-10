from __future__ import annotations

from datetime import datetime
from uuid import UUID

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProductAdminUpdate(BaseModel):
    status: Literal["active", "inactive", "blocked"] | None = None
    preferred: bool | None = None
    blocked: bool | None = None
    reason: str | None = Field(default=None, max_length=1000)


class ProductAdminOut(BaseModel):
    id: UUID
    pharmacy: str
    commercial_name: str
    brand: str | None
    registro_sanitario: str | None
    price: float | None
    currency: str
    availability: str
    commercial_status: str
    preferred: bool = False
    blocked: bool = False
    override_reason: str | None = None
    url: str
    last_seen_at: datetime | None
    verification_status: str = "unknown"
    verification_warnings: list[str] = Field(default_factory=list)
    restriction_flags_verified: list[str] = Field(default_factory=list)
    restriction_flags_inferred: list[str] = Field(default_factory=list)
    label_verified_at: str | None = None
    label_verification_source: str | None = None


class ImportRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    total_scraped: int
    total_accepted: int
    total_rejected: int
    notes: str | None


class IngredientSafetyRuleBase(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    ingredient_pattern: str = Field(min_length=2, max_length=2000)
    restriction_code: str | None = Field(default=None, max_length=80)
    safety_condition_code: str | None = Field(default=None, max_length=80)
    action: Literal["warn", "penalize", "block"] = "warn"
    severity: Literal["low", "medium", "high"] = "medium"
    message: str = Field(min_length=3, max_length=1000)
    active: bool = True
    source: str = Field(default="admin", max_length=120)


class IngredientSafetyRuleCreate(IngredientSafetyRuleBase):
    pass


class IngredientSafetyRuleUpdate(BaseModel):
    ingredient_pattern: str | None = Field(default=None, min_length=2, max_length=2000)
    restriction_code: str | None = Field(default=None, max_length=80)
    safety_condition_code: str | None = Field(default=None, max_length=80)
    action: Literal["warn", "penalize", "block"] | None = None
    severity: Literal["low", "medium", "high"] | None = None
    message: str | None = Field(default=None, min_length=3, max_length=1000)
    active: bool | None = None
    source: str | None = Field(default=None, max_length=120)


class IngredientSafetyRuleOut(IngredientSafetyRuleBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class CatalogQualityOut(BaseModel):
    products_total: int
    active_products: int
    products_with_registro_sanitario: int
    products_with_verified_restriction_flags: int
    products_with_inferred_restriction_flags: int
    products_with_label_source: int
    products_with_recent_label_review: int
    traceability_rate: float
    verified_label_rate: float
    warnings: list[str] = Field(default_factory=list)
