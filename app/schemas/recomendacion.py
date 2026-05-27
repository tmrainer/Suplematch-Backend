from pydantic import BaseModel


class RecommendationItem(BaseModel):
    component_id: str | None = None
    name: str
    condition: str | None = None
    score: float | None = None
    type: str | None = None


class PackComponent(BaseModel):
    component_id: str | None = None
    name: str


class RankedPack(BaseModel):
    pack_id: str
    rank: int
    title: str
    components: list[PackComponent]
    component_ids: list[str]
    component_names: list[str]
    score: float | None = None
    score_final: float | None = None
    score_gnn: float | None = None
    score_coverage: float | None = None
    score_feedback: float | None = None
    feedback_count: int


class ComponentRelation(BaseModel):
    component_a: str
    component_b: str
    type: str


class RecommendationResponse(BaseModel):
    session_id: str
    recommendation_id: str | None = None
    conditions: list[str]
    recommendations: list[RecommendationItem]
    packs_ranked: list[RankedPack]
    sinergias: list[ComponentRelation]
    alertas: list[ComponentRelation]
    combo_seguro: bool
    mensaje: str
    disclaimer: str
    model_versions: dict[str, str]
