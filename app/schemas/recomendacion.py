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
    feedback_count: int
    cta_label: str
    selected_products: list["RecommendedProduct"] = Field(default_factory=list)


class ComponentRelation(BaseModel):
    component_a: str
    component_b: str
    type: str


class RecommendedProduct(BaseModel):
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
    model_versions: dict[str, str]
