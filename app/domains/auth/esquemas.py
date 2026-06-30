from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domains.survey.antropometria import (
    height_to_cm,
    normalize_height_unit,
    normalize_weight_unit,
    weight_to_kg,
)
from app.domains.users.esquemas import UserOut


class RegisterInput(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=160)
    age: int = Field(ge=1, le=120)
    weight_value: float = Field(gt=0, le=500000)
    weight_unit: str = Field(min_length=1, max_length=24)
    height_value: float = Field(gt=0, le=10000)
    height_unit: str = Field(min_length=1, max_length=24)
    display_name: str | None = Field(default=None, max_length=160)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        if not any(char.isalpha() for char in value):
            raise ValueError("La contraseña debe incluir letras.")
        if not any(char.isdigit() for char in value):
            raise ValueError("La contraseña debe incluir números.")
        if value.lower() in {"password123", "suplematch123", "changeme123"}:
            raise ValueError("La contraseña es demasiado común.")
        return value

    @field_validator("first_name", "last_name")
    @classmethod
    def normalize_names(cls, value: str) -> str:
        clean = " ".join(value.strip().split())
        if not clean:
            raise ValueError("Nombre y apellido son obligatorios.")
        return clean

    @field_validator("weight_unit")
    @classmethod
    def normalize_weight_unit(cls, value: str) -> str:
        return normalize_weight_unit(value)

    @field_validator("height_unit")
    @classmethod
    def normalize_height_unit(cls, value: str) -> str:
        return normalize_height_unit(value)

    @model_validator(mode="after")
    def validate_anthropometric_ranges(self):
        weight_kg = weight_to_kg(self.weight_value, self.weight_unit)
        if not 2 <= weight_kg <= 500:
            raise ValueError("Peso fuera de rango razonable.")
        height_cm = height_to_cm(self.height_value, self.height_unit)
        if not 40 <= height_cm <= 260:
            raise ValueError("Estatura fuera de rango razonable.")
        return self

    @property
    def weight_kg(self) -> float:
        return weight_to_kg(self.weight_value, self.weight_unit)

    @property
    def height_cm(self) -> float:
        return height_to_cm(self.height_value, self.height_unit)


class LoginInput(BaseModel):
    email: str
    password: str


class PasswordForgotInput(BaseModel):
    email: str = Field(min_length=5, max_length=320)


class PasswordResetInput(BaseModel):
    token: str = Field(min_length=24, max_length=256)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        return RegisterInput.validate_password_strength(value)


class PasswordChangeInput(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        return RegisterInput.validate_password_strength(value)


class PasswordResetRequestOut(BaseModel):
    message: str
    reset_token: str | None = None


class MessageOut(BaseModel):
    message: str


class RefreshTokenInput(BaseModel):
    refresh_token: str = Field(min_length=24, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut
