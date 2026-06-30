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
    commercial_quality_flags: dict[str, bool] = Field(default_factory=dict)
    product_component_count: int = 1
    component_traceable: str | None = None
    label_verified_at: str | None = None
    label_verification_source: str | None = None
    commercial_confidence_score: float | None = None
    commercial_confidence_level: str | None = None
    commercial_confidence_reasons: str | None = None


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
    products_without_registro_sanitario: int = 0
    products_with_digemid_name_match: int = 0
    products_with_image_ocr_rs: int = 0
    products_with_low_commercial_confidence: int = 0
    products_with_medium_commercial_confidence: int = 0
    products_with_high_commercial_confidence: int = 0
    rejected_by_reason: dict[str, int] = Field(default_factory=dict)
    rejected_by_pharmacy: dict[str, int] = Field(default_factory=dict)
    components_missing_product: list[dict] = Field(default_factory=list)
    components_weak_product: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CatalogCandidateOut(BaseModel):
    candidate_id: str
    component_id: str
    component_name: str
    pharmacy: str
    commercial_name: str
    price: float | None = None
    availability: str | None = None
    registro_sanitario: str | None = None
    url: str | None = None
    sku: str | None = None
    component_traceable: str | None = None
    component_ids_detected: list[str] = Field(default_factory=list)
    component_names_detected: list[str] = Field(default_factory=list)
    match_basis: str | None = None
    needs_catalog_review: bool = False
    catalog_status: str
    promotable: bool = False
    action_reason: str | None = None
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    confidence_notes: list[str] = Field(default_factory=list)


class CatalogCandidateListOut(BaseModel):
    candidates: list[CatalogCandidateOut]
    total: int
    status_counts: dict[str, int] = Field(default_factory=dict)
    recommended_actions: list[str] = Field(default_factory=list)


class CatalogCandidateActionInput(BaseModel):
    status: Literal[
        "candidate_needs_rs",
        "candidate_name_match",
        "approved_for_review",
        "rejected_no_rs",
        "rejected_non_oral",
        "manual_rejected",
    ]
    reason: str = Field(min_length=3, max_length=1000)


class CatalogCandidateActionOut(BaseModel):
    candidate: CatalogCandidateOut
    message: str


class CatalogCandidatePromoteInput(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class CatalogCandidatePromoteOut(BaseModel):
    candidate: CatalogCandidateOut
    product_id: UUID
    message: str


class CatalogJobRunInput(BaseModel):
    mode: Literal["validate_only", "price_only", "update_prices"] = "validate_only"
    limit_per_pharmacy: int = Field(default=1000, ge=1, le=5000)
    pharmacies: list[str] = Field(default_factory=list, max_length=10)
    max_raw_age_hours: int = Field(default=168, ge=1, le=2160)
    import_to_postgres: bool = False


class CatalogJobRunOut(BaseModel):
    accepted: bool
    message: str
    job_id: str | None = None
    status: dict = Field(default_factory=dict)


class CatalogJobStatusOut(BaseModel):
    running: bool
    state: dict | None = None
    current_report: dict | None = None
    alert: dict | None = None
    diff: dict | None = None
    latest_job: dict | None = None
    jobs: list[dict] = Field(default_factory=list)


class CatalogJobCancelOut(BaseModel):
    cancelled: bool
    message: str
    status: dict = Field(default_factory=dict)


class CatalogJobApproveOut(BaseModel):
    approved: bool
    message: str
    result: dict = Field(default_factory=dict)
    status: dict = Field(default_factory=dict)


class ProductPriceSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID | None
    catalog_job_id: UUID | None
    pharmacy: str
    sku: str | None
    commercial_name: str | None
    price: float | None
    currency: str | None
    availability: str | None
    stock: int | None
    registro_sanitario: str | None
    seen_at: datetime
