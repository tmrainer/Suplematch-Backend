from sqlalchemy import func, select
from uuid import UUID

from app.core.security import create_access_token
from app.db.models import LabBiomarkerResult, LabReport, RecommendationSession, User
from app.db.session import SessionLocal
from app.main import create_app
from app.domains.users.repositorio_usuarios import UserRepository
from tests.integration.test_health import asgi_request


def test_lab_text_endpoint_extracts_and_blocks_sensitive_patterns():
    app = create_app()

    status_code, body = asgi_request(
        app,
        "POST",
        "/api/v1/labs/text",
        {
            "consent_health_data": True,
            "raw_text": "Vitamina D 25-OH: 12 ng/mL\nCreatinina: 2.4 mg/dL\nFerritina: 18 ng/mL",
            "source_type": "text",
            "persist": True,
        },
    )

    assert status_code == 200
    assert body["report_id"]
    assert body["safety_level"] == "medical_review_required"
    assert body["commercial_recommendations_blocked"] is True
    assert {item["code"] for item in body["biomarkers"]} >= {"vitamin_d", "creatinine", "ferritin"}
    assert any(signal["supplement"] == "Vitamina D" for signal in body["supplement_signals"])

    with SessionLocal() as db:
        report = db.get(LabReport, UUID(body["report_id"]))
        assert report is not None
        db.delete(report)
        db.commit()


def test_lab_text_requires_consent():
    app = create_app()

    status_code, body = asgi_request(
        app,
        "POST",
        "/api/v1/labs/text",
        {
            "consent_health_data": False,
            "raw_text": "Vitamina D 25-OH: 12 ng/mL",
            "source_type": "text",
            "persist": False,
        },
    )

    assert status_code == 422
    assert body["detail"]


def test_authenticated_user_can_export_and_delete_lab_health_data():
    email = "labs-export-test@suplematch.test"
    app = create_app()

    with SessionLocal() as db:
        existing = db.scalar(select(User).where(User.email == email))
        if existing is not None:
            db.delete(existing)
            db.commit()

    status_code, auth_body = asgi_request(
        app,
        "POST",
        "/api/v1/auth/register",
        {
            "email": email,
            "password": "LabsTest123",
            "first_name": "Labs",
            "last_name": "Export",
            "age": 30,
            "weight_value": 154,
            "weight_unit": "lb",
            "height_value": 170,
            "height_unit": "cm",
            "display_name": "Labs Export",
        },
    )
    assert status_code == 200
    token = auth_body["access_token"]

    status_code, body = asgi_request(
        app,
        "POST",
        "/api/v1/labs/text",
        {
            "consent_health_data": True,
            "raw_text": "Vit D 25 OH 12 ng/mL ref 20 - 100\nFerritina 18 ng/mL 30 - 300",
            "source_type": "text",
            "persist": True,
        },
        headers={"authorization": f"Bearer {token}"},
    )
    assert status_code == 200
    report_id = body["report_id"]
    assert body["biomarkers"][0]["reference_low"] is not None

    status_code, export_body = asgi_request(app, "GET", "/api/v1/labs/me/export", headers={"authorization": f"Bearer {token}"})
    assert status_code == 200
    assert export_body["reports"]
    assert export_body["reports"][0]["raw_text"]

    status_code, delete_body = asgi_request(app, "DELETE", f"/api/v1/labs/me/{report_id}", headers={"authorization": f"Bearer {token}"})
    assert status_code == 200
    assert delete_body["message"]

    with SessionLocal() as db:
        report = db.get(LabReport, UUID(report_id))
        assert report is not None
        assert report.status == "deleted"
        assert report.raw_text is None
        count = db.scalar(
            select(func.count())
            .select_from(LabBiomarkerResult)
            .where(LabBiomarkerResult.lab_report_id == report.id)
        )
        assert count == 0
        user = db.scalar(select(User).where(User.email == email))
        if user is not None:
            db.delete(user)
        db.commit()


def test_recommendation_uses_lab_results_for_safety_and_signals():
    recommendation_id = "rec_test_lab_results"
    email = "recommend-labs@suplematch.test"

    with SessionLocal() as db:
        existing = db.scalar(
            select(RecommendationSession).where(RecommendationSession.recommendation_id == recommendation_id)
        )
        if existing is not None:
            db.delete(existing)
        existing_user = db.scalar(select(User).where(User.email == email))
        if existing_user is not None:
            db.delete(existing_user)
        db.commit()
        user = UserRepository(db).create_user(email=email, password="ChangeMe123!", display_name="Labs Recommend")
        token = create_access_token(str(user.id), {"roles": ["user"]})
        db.commit()

    def pipeline(_payload, verbose=False):
        return {
            "recommendation_id": recommendation_id,
            "condiciones": [],
            "recomendaciones": [],
            "packs_ranked": [],
            "sinergias": [],
            "alertas": [],
            "combo_seguro": True,
            "mensaje": "OK",
        }

    app = create_app()
    app.state.models = {"pipeline_vitaminas": pipeline}
    payload = {
        "edad_rango": "31_50",
        "horas_sueno": "5_7h",
        "frecuencia_ejercicio": "1_2_semana",
        "dieta": "regular",
        "fatiga": "a_menudo",
        "exposicion_solar": "menos_15min",
        "frecuencia_enfermedad": "1_2_anio",
        "estres": "moderado",
        "alcohol": "ocasional",
        "toma_suplementos": "no",
        "suplementos_actuales": [],
        "restricciones": ["sin_restricciones"],
        "condiciones_seguridad": ["ninguna"],
        "lab_results": [
            {"code": "vitamin_d", "value": 12, "unit": "ng/mL"},
            {"code": "creatinine", "value": 2.3, "unit": "mg/dL"},
        ],
    }

    status_code, body = asgi_request(
        app,
        "POST",
        "/api/v1/recommend",
        payload,
        headers={"authorization": f"Bearer {token}"},
    )

    assert status_code == 200
    assert body["lab_analysis"]
    assert body["safety_level"] == "medical_review_required"
    assert body["commercial_recommendations_blocked"] is True
    assert body["recommendations"][0]["condition"] == "LAB_RESULT"
    assert body["recommendations"][0]["products"] == []

    with SessionLocal() as db:
        session = db.scalar(
            select(RecommendationSession).where(RecommendationSession.recommendation_id == recommendation_id)
        )
        if session is not None:
            db.delete(session)
        user = db.scalar(select(User).where(User.email == email))
        if user is not None:
            db.delete(user)
        db.commit()
