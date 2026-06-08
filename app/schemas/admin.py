from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProductAdminUpdate(BaseModel):
    status: str | None = Field(default=None, max_length=40)
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
    url: str
    last_seen_at: datetime | None


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
