from typing import Any
from pydantic import BaseModel, Field


class FeatureDriver(BaseModel):
    feature: str
    label: str
    value: Any
    value_label: str
    impact: str


class ConditionExplanation(BaseModel):
    condition: str
    probability: float
    drivers: list[FeatureDriver]


class ConditionDisplay(BaseModel):
    code: str
    display_name: str
    level: str
    probability: float
    icon_key: str


class RecommendationItem(BaseModel):
    component_id: str | None = None
    name: str
    display_name: str
    condition: str | None = None
    condition_display: str | None = None
    score: float | None = None
    type: str | None = None
    type_display: str | None = None
    reason: str
    dosage_hint: str
    priority: str
    icon_key: str
    products: list["RecommendedProduct"] = Field(default_factory=list)
    already_taking: bool = False
    safety_note: str | None = None


class PackComponent(BaseModel):
    component_id: str | None = None
    name: str
    display_name: str
    icon_key: str


class RankedPack(BaseModel):
    pack_id: str
    rank: int
    title: str
    subtitle: str
    components: list[PackComponent]
    component_ids: list[str]
    component_names: list[str]
    score: float | None = None
    score_final: float | None = None
    score_gnn: float | None = None
    score_coverage: float | None = None
    score_feedback: float | None = None
    score_reviews: float | None = None
    score_exposure: float | None = None
    score_products: float | None = None
    score_diversity: float | None = None
    feedback_count: int
    reviews_count: int = 0
    exposure_count: int = 0
    cta_label: str
    selected_products: list["RecommendedProduct"] = Field(default_factory=list)


class ComponentRelation(BaseModel):
    component_a: str
    component_b: str
    type: str


class RecommendedProduct(BaseModel):
    product_id: str | None = None
    pharmacy: str
    commercial_name: str
    formal_name: str | None = None
    registro_sanitario: str
    digemid_producto: str | None = None
    component_id: str
    ingredient: str
    amount: str | None = None
    unit: str | None = None
    amount_mg: float | None = None
    component_match_score: float | None = None
    price: float
    currency: str
    availability: str
    url: str
    sku: str | None = None
    brand: str | None = None
    regulatory_status: str
    stock: int | None = None
    last_seen_at: str | None = None
    product_score: float | None = None
    catalog_preferred: bool = False
    catalog_blocked: bool = False
    catalog_override_reason: str | None = None
    match_score: float | None = None
    review_score: float | None = None
    review_count: int = 0
    avg_rating: float | None = None
    bayesian_review_score: float | None = None
    price_score: float | None = None
    stock_score: float | None = None
    traceability_score: float | None = None
    pharmacy_diversity_score: float | None = None
    freshness_score: float | None = None
    restriction_penalty: float | None = None
    ingredient_safety_penalty: float | None = None
    restriction_boost: float | None = None
    preferred_boost: float | None = None
    product_safety_blocked: bool = False
    product_safety_rules: list[dict[str, Any]] = Field(default_factory=list)
    restriction_flags: list[str] = Field(default_factory=list)
    restriction_flags_verified: list[str] = Field(default_factory=list)
    restriction_flags_inferred: list[str] = Field(default_factory=list)
    restriction_warnings: list[str] = Field(default_factory=list)
    label_verified_at: str | None = None
    label_verification_source: str | None = None
    selection_reasons: list[str] = Field(default_factory=list)
    selection_metrics: dict[str, Any] = Field(default_factory=dict)


class RecommendationResponse(BaseModel):
    session_id: str
    recommendation_id: str | None = None
    conditions: list[str]
    conditions_display: list[ConditionDisplay]
    explainability: list[ConditionExplanation] = Field(default_factory=list)
    recommendations: list[RecommendationItem]
    packs_ranked: list[RankedPack]
    sinergias: list[ComponentRelation]
    alertas: list[ComponentRelation]
    combo_seguro: bool
    mensaje: str
    disclaimer: str
    profile_warnings: list[str] = Field(default_factory=list)
    safety_level: str = "normal"
    safety_actions: list[str] = Field(default_factory=list)
    commercial_recommendations_blocked: bool = False
    lab_analysis: dict[str, Any] | None = None
    model_versions: dict[str, str]
