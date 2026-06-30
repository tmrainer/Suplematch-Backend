from typing import Any, Literal
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


class CategorizedConditionResult(BaseModel):
    code: str
    display_name: str
    kind: Literal["biomedical_risk", "nutrition_risk", "wellness_priority", "safety_flag", "context"]
    probability: float | None = None
    level: str
    evidence_group: str = "unknown"
    confidence_label: Literal["baja", "media", "alta"] = "baja"
    recommendation_strength: Literal["no_convertir", "baja", "media", "alta", "bloqueada"] = "baja"
    benchmark_status: str = "not_evaluated"
    validation_source: str = "internal_rules"
    primary_signal_group: str = "unknown"
    signal_strength: Literal["baja", "media", "alta"] = "baja"
    signal_groups: dict[str, Any] = Field(default_factory=dict)
    drivers: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    model_probability: float | None = None
    rule_score: float | None = None
    calibrated_by_rules: bool = False
    allowed_for_commercial_recommendation: bool = True
    requires_disclaimer: bool = True
    explanation: str


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
    condition_probability: float | None = None
    evidence_strength: str | None = None
    evidence_type: str | None = None
    evidence_weight: float | None = None
    evidence_score: float | None = None
    evidence_factors: dict[str, Any] = Field(default_factory=dict)
    recommendation_role: str | None = None
    requires_lab: str | None = None
    risk_level: str | None = None
    source_quality: str | None = None
    missing_data_penalty: float | None = None
    source_ids: list[str] = Field(default_factory=list)
    rationale: str | None = None
    component_profile_role: str | None = None
    adult_upper_limit: str | None = None
    upper_limit_unit: str | None = None
    upper_limit_note: str | None = None
    dose_guidance: str | None = None
    age_sex_note: str | None = None
    pregnancy_lactation_note: str | None = None
    contraindications: list[str] = Field(default_factory=list)
    interaction_notes: str | None = None
    component_safety_level: str | None = None
    component_profile_source_ids: list[str] = Field(default_factory=list)
    component_profile_rationale: str | None = None
    component_lookup_candidates: list[str] = Field(default_factory=list)
    life_stage_guidance: list[dict[str, Any]] = Field(default_factory=list)
    interaction_rules: list[dict[str, Any]] = Field(default_factory=list)
    claim_evidence: list[dict[str, Any]] = Field(default_factory=list)
    model2_ranker: str | None = None
    model2_stage: str | None = None
    graph_similarity: float | None = None
    ranking_reason: str | None = None
    recommendation_source: str | None = None
    commercial_eligible: bool = True
    commercial_recommendation_blocked: bool = False
    commercial_block_reason: str | None = None


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
    component_a_id: str | None = None
    component_b_id: str | None = None
    explanation: str | None = None


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
    image_url: str | None = None
    image_source: str | None = None
    image_local_path: str | None = None
    regulatory_status: str
    stock: int | None = None
    last_seen_at: str | None = None
    commercial_score: float | None = None
    commercial_score_version: str | None = None
    commercial_score_breakdown: dict[str, Any] = Field(default_factory=dict)
    commercial_quality_flags: dict[str, bool] = Field(default_factory=dict)
    commercial_decision: str | None = None
    component_match_type: str | None = None
    product_score: float | None = None
    catalog_preferred: bool = False
    catalog_blocked: bool = False
    catalog_override_reason: str | None = None
    match_score: float | None = None
    unit_preference_score: float | None = None
    review_score: float | None = None
    product_review_score: float | None = None
    review_count: int = 0
    avg_rating: float | None = None
    avg_effectiveness_score: float | None = None
    avg_tolerance_score: float | None = None
    avg_price_value_score: float | None = None
    bayesian_review_score: float | None = None
    price_score: float | None = None
    stock_score: float | None = None
    traceability_score: float | None = None
    catalog_quality_score: float | None = None
    pharmacy_diversity_score: float | None = None
    freshness_score: float | None = None
    exposure_score: float | None = None
    product_exposure_score: float | None = None
    pharmacy_exposure_score: float | None = None
    product_exposure_count: int = 0
    pharmacy_exposure_count: int = 0
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
    condition_results: list[CategorizedConditionResult] = Field(default_factory=list)
    wellness_priorities: list[CategorizedConditionResult] = Field(default_factory=list)
    safety_flags: list[CategorizedConditionResult] = Field(default_factory=list)
    lab_analysis: dict[str, Any] | None = None
    model_versions: dict[str, str]
