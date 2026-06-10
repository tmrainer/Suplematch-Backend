from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.schemas.user import UserOut


class RegisterInput(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=8, max_length=128)
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
