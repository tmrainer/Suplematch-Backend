from pydantic import BaseModel, Field


class FeedbackInput(BaseModel):
    recommendation_id: str
    pack_id: str | None = None
    component_ids: list[str] = Field(default_factory=list)
    rating: int = Field(ge=1, le=5)
    conditions: list[str] = Field(default_factory=list)
    comment: str | None = None
