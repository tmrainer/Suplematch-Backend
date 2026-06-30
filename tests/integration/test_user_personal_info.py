from sqlalchemy import select

from app.db.models import User, UserPersonalInfo
from app.db.session import SessionLocal
from app.main import create_app
from tests.integration.test_health import asgi_request


def _cleanup_user(email: str) -> None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is not None:
            db.delete(user)
            db.commit()


def _register(app, email: str, display_name: str) -> str:
    status_code, body = asgi_request(
        app,
        "POST",
        "/api/v1/auth/register",
        {
            "email": email,
            "password": "Personal123",
            "first_name": display_name.split(" ", 1)[0],
            "last_name": display_name.split(" ", 1)[-1],
            "age": 29,
            "weight_value": 70,
            "weight_unit": "kg",
            "height_value": 170,
            "height_unit": "cm",
            "display_name": display_name,
        },
    )
    assert status_code == 200
    return body["access_token"]


def test_personal_info_is_persisted_and_isolated_per_user():
    email_a = "personal-a@suplematch.test"
    email_b = "personal-b@suplematch.test"
    _cleanup_user(email_a)
    _cleanup_user(email_b)
    app = create_app()
    token_a = _register(app, email_a, "Persona A")
    token_b = _register(app, email_b, "Persona B")

    status_code, body_a = asgi_request(
        app,
        "PUT",
        "/api/v1/users/me/personal",
        {
            "first_name": "Ana",
            "last_name": "Lopez",
            "phone": "+51999999991",
            "country": "PE",
            "city": "Lima",
            "district": "Miraflores",
            "date_of_birth": "1998-04-12",
            "document_type": "DNI",
            "document_number": "12345678",
            "preferences": {"preferred_language": "es"},
        },
        headers={"authorization": f"Bearer {token_a}"},
    )
    assert status_code == 200
    assert body_a["first_name"] == "Ana"
    assert body_a["preferences"]["preferred_language"] == "es"

    status_code, body_b = asgi_request(
        app,
        "PUT",
        "/api/v1/users/me/personal",
        {
            "first_name": "Bruno",
            "last_name": "Perez",
            "phone": "+51999999992",
            "country": "PE",
            "city": "Arequipa",
        },
        headers={"authorization": f"Bearer {token_b}"},
    )
    assert status_code == 200
    assert body_b["first_name"] == "Bruno"

    status_code, me_a = asgi_request(
        app,
        "GET",
        "/api/v1/users/me",
        headers={"authorization": f"Bearer {token_a}"},
    )
    status_code_b, me_b = asgi_request(
        app,
        "GET",
        "/api/v1/users/me",
        headers={"authorization": f"Bearer {token_b}"},
    )
    assert status_code == 200
    assert status_code_b == 200
    assert me_a["personal_info"]["first_name"] == "Ana"
    assert me_b["personal_info"]["first_name"] == "Bruno"
    assert me_a["personal_info"]["phone"] != me_b["personal_info"]["phone"]

    with SessionLocal() as db:
        user_a = db.scalar(select(User).where(User.email == email_a))
        user_b = db.scalar(select(User).where(User.email == email_b))
        assert user_a is not None
        assert user_b is not None
        info_a = db.get(UserPersonalInfo, user_a.id)
        info_b = db.get(UserPersonalInfo, user_b.id)
        assert info_a is not None
        assert info_b is not None
        assert info_a.user_id == user_a.id
        assert info_b.user_id == user_b.id
        assert info_a.first_name == "Ana"
        assert info_b.first_name == "Bruno"

    status_code, cleared = asgi_request(
        app,
        "DELETE",
        "/api/v1/users/me/personal",
        headers={"authorization": f"Bearer {token_a}"},
    )
    assert status_code == 200
    assert cleared["first_name"] is None
    assert cleared["preferences"] == {}

    status_code, still_b = asgi_request(
        app,
        "GET",
        "/api/v1/users/me/personal",
        headers={"authorization": f"Bearer {token_b}"},
    )
    assert status_code == 200
    assert still_b["first_name"] == "Bruno"

    _cleanup_user(email_a)
    _cleanup_user(email_b)


def test_user_can_export_and_delete_consolidated_health_data():
    email = "health-data-export@suplematch.test"
    _cleanup_user(email)
    app = create_app()
    token = _register(app, email, "Health Data")

    status_code, _ = asgi_request(
        app,
        "PUT",
        "/api/v1/users/me/profile",
        {
            "diet_type": "vegano",
            "age_years": 31,
            "weight_value": 68,
            "weight_unit": "kg",
            "weight_kg": 68,
            "height_value": 168,
            "height_unit": "cm",
            "height_cm": 168,
            "health_goals": {"objetivos": ["energia"], "presupuesto": "bajo"},
            "allergies": {"restricciones": ["alergia_pescado_mariscos"]},
            "medical_warnings": {"condiciones_seguridad": ["enfermedad_renal"]},
        },
        headers={"authorization": f"Bearer {token}"},
    )
    assert status_code == 200

    status_code, lab = asgi_request(
        app,
        "POST",
        "/api/v1/labs/text",
        {
            "consent_health_data": True,
            "raw_text": "Vitamina D 25-OH 18 ng/mL referencia 30 - 100\nCreatinina 1.9 mg/dL 0.6 - 1.3",
            "source_type": "text",
            "persist": True,
        },
        headers={"authorization": f"Bearer {token}"},
    )
    assert status_code == 200
    assert lab["report_id"]

    status_code, exported = asgi_request(
        app,
        "GET",
        "/api/v1/users/me/health-data/export",
        headers={"authorization": f"Bearer {token}"},
    )
    assert status_code == 200
    assert exported["profile"]["diet_type"] == "vegano"
    assert exported["profile"]["height_cm"] == 168
    assert exported["lab_reports"]
    assert exported["lab_reports"][0]["raw_text"]

    status_code, deleted = asgi_request(
        app,
        "DELETE",
        "/api/v1/users/me/health-data",
        headers={"authorization": f"Bearer {token}"},
    )
    assert status_code == 200
    assert deleted["lab_reports_deleted"] >= 1
    assert deleted["profile_health_fields_cleared"] is True

    status_code, exported_after = asgi_request(
        app,
        "GET",
        "/api/v1/users/me/health-data/export",
        headers={"authorization": f"Bearer {token}"},
    )
    assert status_code == 200
    assert exported_after["profile"]["diet_type"] is None
    assert exported_after["profile"]["height_cm"] is None
    assert exported_after["lab_reports"] == []

    _cleanup_user(email)
