from __future__ import annotations

from datetime import date
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class UserProfileOut(BaseModel):
    birth_year: int | None = None
    sex: str | None = None
    diet_type: str | None = None
    activity_level: str | None = None
    age_years: int | None = None
    weight_value: float | None = None
    weight_unit: str | None = None
    weight_kg: float | None = None
    height_value: float | None = None
    height_unit: str | None = None
    height_cm: float | None = None
    health_goals: dict = Field(default_factory=dict)
    allergies: dict = Field(default_factory=dict)
    medical_warnings: dict = Field(default_factory=dict)


class UserProfileUpdate(BaseModel):
    birth_year: int | None = Field(default=None, ge=1900, le=2100)
    sex: str | None = Field(default=None, max_length=32)
    diet_type: str | None = Field(default=None, max_length=64)
    activity_level: str | None = Field(default=None, max_length=64)
    age_years: int | None = Field(default=None, ge=0, le=120)
    weight_value: float | None = Field(default=None, gt=0, le=1000)
    weight_unit: str | None = Field(default=None, max_length=24)
    weight_kg: float | None = Field(default=None, gt=0, le=500)
    height_value: float | None = Field(default=None, gt=0, le=10000)
    height_unit: str | None = Field(default=None, max_length=24)
    height_cm: float | None = Field(default=None, gt=0, le=300)
    health_goals: dict | None = None
    allergies: dict | None = None
    medical_warnings: dict | None = None


class UserPersonalInfoOut(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    country: str | None = None
    city: str | None = None
    district: str | None = None
    address_line: str | None = None
    date_of_birth: date | None = None
    document_type: str | None = None
    document_number: str | None = None
    preferences: dict = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class UserPersonalInfoUpdate(BaseModel):
    first_name: str | None = Field(default=None, max_length=120)
    last_name: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=40)
    country: str | None = Field(default=None, max_length=80)
    city: str | None = Field(default=None, max_length=120)
    district: str | None = Field(default=None, max_length=120)
    address_line: str | None = Field(default=None, max_length=500)
    date_of_birth: date | None = None
    document_type: str | None = Field(default=None, max_length=40)
    document_number: str | None = Field(default=None, max_length=80)
    preferences: dict | None = None


class UserOut(BaseModel):
    id: UUID
    email: str
    display_name: str | None = None
    status: str
    roles: list[str] = Field(default_factory=list)
    profile: UserProfileOut | None = None
    personal_info: UserPersonalInfoOut | None = None
    created_at: datetime
    last_login_at: datetime | None = None


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=160)
    status: str | None = Field(default=None, max_length=32)


class UserHealthDataExportOut(BaseModel):
    exported_at: datetime
    user_id: UUID
    profile: UserProfileOut | None = None
    personal_info: UserPersonalInfoOut | None = None
    lab_reports: list[dict] = Field(default_factory=list)
    recommendation_profile_snapshots: list[dict] = Field(default_factory=list)


class UserHealthDataDeleteOut(BaseModel):
    message: str
    lab_reports_deleted: int
    profile_health_fields_cleared: bool
