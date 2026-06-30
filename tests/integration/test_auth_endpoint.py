from sqlalchemy import select

from app.core.config import settings
from app.db.models import PasswordResetToken, RefreshToken, User
from app.db.session import SessionLocal
from app.main import create_app
from tests.integration.test_health import asgi_request


def _registration_payload(email: str, display_name: str) -> dict:
    first_name, _, last_name = display_name.partition(" ")
    return {
        "email": email,
        "password": "Initial123",
        "first_name": first_name or "Demo",
        "last_name": last_name or "User",
        "age": 28,
        "weight_value": 70,
        "weight_unit": "kg",
        "height_value": 170,
        "height_unit": "cm",
        "display_name": display_name,
    }


def _cleanup_user(email: str) -> None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is not None:
            db.delete(user)
            db.commit()


def test_password_reset_and_change_flow():
    email = "auth-reset-test@suplematch.test"
    _cleanup_user(email)
    app = create_app()

    status_code, body = asgi_request(
        app,
        "POST",
        "/api/v1/auth/register",
        _registration_payload(email, "Reset Test"),
    )
    assert status_code == 200
    token = body["access_token"]
    refresh_token = body["refresh_token"]
    assert refresh_token

    old_return_token = settings.PASSWORD_RESET_RETURN_TOKEN
    settings.PASSWORD_RESET_RETURN_TOKEN = True
    try:
        status_code, body = asgi_request(app, "POST", "/api/v1/auth/forgot-password", {"email": email})
        assert status_code == 200
        assert body["reset_token"]

        status_code, body = asgi_request(
            app,
            "POST",
            "/api/v1/auth/reset-password",
            {"token": body["reset_token"], "new_password": "Changed123"},
        )
        assert status_code == 200
        assert body["message"]
    finally:
        settings.PASSWORD_RESET_RETURN_TOKEN = old_return_token

    status_code, _body = asgi_request(
        app,
        "POST",
        "/api/v1/auth/refresh",
        {"refresh_token": refresh_token},
    )
    assert status_code == 401

    status_code, body = asgi_request(app, "POST", "/api/v1/auth/login", {"email": email, "password": "Changed123"})
    assert status_code == 200
    token = body["access_token"]
    refresh_token = body["refresh_token"]

    status_code, body = asgi_request(
        app,
        "POST",
        "/api/v1/auth/change-password",
        {"current_password": "Changed123", "new_password": "ChangedAgain123"},
        headers={"authorization": f"Bearer {token}"},
    )
    assert status_code == 200

    status_code, _body = asgi_request(
        app,
        "POST",
        "/api/v1/auth/refresh",
        {"refresh_token": refresh_token},
    )
    assert status_code == 401

    status_code, _body = asgi_request(app, "POST", "/api/v1/auth/login", {"email": email, "password": "ChangedAgain123"})
    assert status_code == 200

    with SessionLocal() as db:
        reset_tokens = list(db.scalars(select(PasswordResetToken).join(User).where(User.email == email)))
        assert reset_tokens
        assert any(item.used_at is not None for item in reset_tokens)
        refresh_tokens = list(db.scalars(select(RefreshToken).join(User).where(User.email == email)))
        assert refresh_tokens
        assert any(item.revoked_at is not None for item in refresh_tokens)

    _cleanup_user(email)


def test_register_requires_personal_fields_and_normalizes_weight():
    email = "auth-register-profile@suplematch.test"
    _cleanup_user(email)
    app = create_app()

    status_code, body = asgi_request(
        app,
        "POST",
        "/api/v1/auth/register",
        {
            "email": email,
            "password": "Initial123",
            "first_name": "Ana",
            "last_name": "Lopez",
            "age": 25,
            "weight_value": 154,
            "weight_unit": "lb",
            "height_value": 5.58,
            "height_unit": "ft",
        },
    )

    assert status_code == 200
    assert body["user"]["display_name"] == "Ana Lopez"
    assert body["user"]["personal_info"]["first_name"] == "Ana"
    assert body["user"]["personal_info"]["last_name"] == "Lopez"
    assert body["user"]["profile"]["age_years"] == 25
    assert body["user"]["profile"]["weight_unit"] == "lb"
    assert body["user"]["profile"]["weight_value"] == 154
    assert body["user"]["profile"]["weight_kg"] == 69.8532
    assert body["user"]["profile"]["height_unit"] == "ft"
    assert body["user"]["profile"]["height_value"] == 5.58
    assert body["user"]["profile"]["height_cm"] == 170.08

    _cleanup_user(email)


def test_register_rejects_missing_required_profile_fields():
    app = create_app()

    status_code, body = asgi_request(
        app,
        "POST",
        "/api/v1/auth/register",
        {"email": "missing-profile@suplematch.test", "password": "Initial123"},
    )

    assert status_code == 422
    assert body["detail"]


def test_refresh_token_rotation_and_logout_flow():
    email = "auth-refresh-test@suplematch.test"
    _cleanup_user(email)
    app = create_app()

    status_code, body = asgi_request(
        app,
        "POST",
        "/api/v1/auth/register",
        _registration_payload(email, "Refresh Test"),
    )
    assert status_code == 200
    original_refresh = body["refresh_token"]

    status_code, body = asgi_request(
        app,
        "POST",
        "/api/v1/auth/refresh",
        {"refresh_token": original_refresh},
    )
    assert status_code == 200
    rotated_refresh = body["refresh_token"]
    assert rotated_refresh != original_refresh

    status_code, _body = asgi_request(
        app,
        "POST",
        "/api/v1/auth/refresh",
        {"refresh_token": original_refresh},
    )
    assert status_code == 401

    status_code, body = asgi_request(
        app,
        "POST",
        "/api/v1/auth/logout",
        {"refresh_token": rotated_refresh},
    )
    assert status_code == 200
    assert body["message"]

    status_code, _body = asgi_request(
        app,
        "POST",
        "/api/v1/auth/refresh",
        {"refresh_token": rotated_refresh},
    )
    assert status_code == 401

    _cleanup_user(email)
