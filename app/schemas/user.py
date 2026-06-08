from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class UserProfileOut(BaseModel):
    birth_year: int | None = None
    sex: str | None = None
    diet_type: str | None = None
    activity_level: str | None = None
    health_goals: dict = Field(default_factory=dict)
    allergies: dict = Field(default_factory=dict)
    medical_warnings: dict = Field(default_factory=dict)


class UserProfileUpdate(BaseModel):
    birth_year: int | None = Field(default=None, ge=1900, le=2100)
    sex: str | None = Field(default=None, max_length=32)
    diet_type: str | None = Field(default=None, max_length=64)
    activity_level: str | None = Field(default=None, max_length=64)
    health_goals: dict | None = None
    allergies: dict | None = None
    medical_warnings: dict | None = None


class UserOut(BaseModel):
    id: UUID
    email: str
    display_name: str | None = None
    status: str
    roles: list[str] = Field(default_factory=list)
    profile: UserProfileOut | None = None
    created_at: datetime
    last_login_at: datetime | None = None


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=160)
    status: str | None = Field(default=None, max_length=32)
