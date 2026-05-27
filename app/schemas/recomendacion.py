from pydantic import BaseModel


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


class ComponentRelation(BaseModel):
    component_a: str
    component_b: str
    type: str


class RecommendationResponse(BaseModel):
    session_id: str
    recommendation_id: str | None = None
    conditions: list[str]
    conditions_display: list[ConditionDisplay]
    recommendations: list[RecommendationItem]
    packs_ranked: list[RankedPack]
    sinergias: list[ComponentRelation]
    alertas: list[ComponentRelation]
    combo_seguro: bool
    mensaje: str
    disclaimer: str
    model_versions: dict[str, str]
