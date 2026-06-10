from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


LabSourceType = Literal["manual", "text", "pdf", "image"]


class LabBiomarkerInput(BaseModel):
    code: str = Field(min_length=2, max_length=80)
    value: float = Field(gt=0)
    unit: str = Field(min_length=1, max_length=40)
    reference_low: float | None = None
    reference_high: float | None = None

    @model_validator(mode="after")
    def validate_reference_range(self):
        if self.reference_low is not None and self.reference_high is not None:
            if self.reference_low >= self.reference_high:
                raise ValueError("reference_low debe ser menor que reference_high.")
        return self


class LabManualInput(BaseModel):
    consent_health_data: bool
    biomarkers: list[LabBiomarkerInput] = Field(min_length=1, max_length=40)
    source_note: str | None = Field(default=None, max_length=500)
    persist: bool = True

    @model_validator(mode="after")
    def require_consent(self):
        if not self.consent_health_data:
            raise ValueError("Debe aceptar el consentimiento para procesar datos de salud.")
        return self


class LabTextInput(BaseModel):
    consent_health_data: bool
    raw_text: str = Field(min_length=10, max_length=20000)
    source_type: LabSourceType = "text"
    persist: bool = True

    @model_validator(mode="after")
    def require_consent(self):
        if not self.consent_health_data:
            raise ValueError("Debe aceptar el consentimiento para procesar datos de salud.")
        return self


class LabBiomarkerOut(BaseModel):
    code: str
    display_name: str
    value: float
    unit: str
    reference_low: float | None = None
    reference_high: float | None = None
    status: str
    severity: str
    confidence: float = 1.0
    source_text: str | None = None


class LabAnalysisOut(BaseModel):
    report_id: UUID | None = None
    source_type: str
    biomarkers: list[LabBiomarkerOut]
    warnings: list[str] = Field(default_factory=list)
    safety_level: str
    safety_actions: list[str] = Field(default_factory=list)
    commercial_recommendations_blocked: bool
    supplement_signals: list[dict] = Field(default_factory=list)
    recommendation_notes: list[str] = Field(default_factory=list)
    extracted_text_preview: str | None = None
    ocr_engine: str | None = None
    created_at: datetime | None = None


class LabReportHistoryOut(BaseModel):
    id: UUID
    source_type: str
    status: str
    created_at: datetime
    biomarker_count: int
    safety_level: str
    commercial_recommendations_blocked: bool
    warnings: list[str] = Field(default_factory=list)
    biomarkers: list[LabBiomarkerOut] = Field(default_factory=list)
    supplement_signals: list[dict] = Field(default_factory=list)
    ocr_engine: str | None = None
    file_name: str | None = None


class LabDataExportOut(BaseModel):
    exported_at: datetime
    user_id: UUID
    reports: list[dict] = Field(default_factory=list)
