import pytest
from sqlalchemy import func, select
from uuid import UUID

from app.core.security import create_access_token
from app.db.models import LabBiomarkerResult, LabReport, RecommendationSession, User
from app.db.session import SessionLocal
from app.main import create_app
from app.domains.users.repositorio_usuarios import UserRepository
from tests.integration.test_health import asgi_request



# /recommend necesita los .pkl (no versionados) y torch. En CI limpio estos tests se omiten.
def _models_ready() -> bool:
    import importlib.util

    from app.ml.model_loader import check_model_artifacts

    return bool(check_model_artifacts()["ready"]) and importlib.util.find_spec("torch") is not None


needs_models = pytest.mark.skipif(not _models_ready(), reason="artefactos de modelo o torch no disponibles")

def test_lab_text_endpoint_extracts_and_blocks_sensitive_patterns():
    """Anonimo: analiza y bloquea, pero NO persiste (datos de salud sin usuario que pueda borrarlos)."""
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
    assert body["report_id"] is None
    assert body["persisted"] is False
    assert any("no se guardo" in note.lower() for note in body["recommendation_notes"])
    assert body["safety_level"] == "medical_review_required"
    assert body["commercial_recommendations_blocked"] is True
    assert {item["code"] for item in body["biomarkers"]} >= {"vitamin_d", "creatinine", "ferritin"}
    assert any(signal["supplement"] == "Vitamina D" for signal in body["supplement_signals"])


def test_lab_text_persists_for_authenticated_user_with_redacted_pii_and_consent_record():
    app = create_app()
    email = "labs-persist-test@example.com"
    with SessionLocal() as db:
        existing = db.scalar(select(User).where(User.email == email))
        if existing is not None:
            db.delete(existing)
            db.commit()
        user = UserRepository(db).create_user(email=email, password="ChangeMe123!", display_name="Labs Persist")
        token = create_access_token(str(user.id), {"roles": ["user"]})
        user_id = user.id

    status_code, body = asgi_request(
        app,
        "POST",
        "/api/v1/labs/text",
        {
            "consent_health_data": True,
            "raw_text": "Paciente: Juan Perez DNI 12345678\nHemoglobina 11.2 g/dL\nVitamina D 25-OH: 18 ng/mL",
            "source_type": "text",
            "persist": True,
            "patient_context": {"sex": "female", "age": 30},
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert status_code == 200
    assert body["persisted"] is True and body["report_id"]
    hb = next(item for item in body["biomarkers"] if item["code"] == "hemoglobin")
    assert hb["status"] == "low" and hb["reference_group"] == "female_15+"

    with SessionLocal() as db:
        report = db.get(LabReport, UUID(body["report_id"]))
        assert report is not None
        assert "Juan Perez" not in (report.raw_text or "") and "12345678" not in (report.raw_text or "")
        assert report.parsed_payload_json["consent"]["accepted"] is True
        assert report.parsed_payload_json["consent"]["text_version"]
        db.delete(report)
        db.commit()
        user = db.get(User, user_id)
        if user is not None:
            db.delete(user)
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


@needs_models
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
