from sqlalchemy import select

from app.core.security import create_access_token
from app.db.models import RecommendationSession, User
from app.db.session import SessionLocal
from app.main import create_app
from app.repositories.user_repository import UserRepository
from tests.integration.test_health import asgi_request


def _survey_payload():
    return {
        "edad_rango": "31_50",
        "horas_sueno": "5_7h",
        "frecuencia_ejercicio": "1_2_semana",
        "dieta": "regular",
        "fatiga": "a_menudo",
        "exposicion_solar": "menos_15min",
        "frecuencia_enfermedad": "1_2_anio",
        "estres": "moderado",
        "alcohol": "ocasional",
    }


def test_recommend_endpoint_returns_normalized_response():
    recommendation_id = "rec_test_normalized_response"

    with SessionLocal() as db:
        existing = db.scalar(
            select(RecommendationSession).where(RecommendationSession.recommendation_id == recommendation_id)
        )
        if existing is not None:
            db.delete(existing)
            db.commit()

    def pipeline(_payload, verbose=False):
        return {
            "recommendation_id": recommendation_id,
            "condiciones": ["DEFICIT_VIT_D"],
            "recomendaciones": [
                {
                    "component_id": "cmp_vit_d",
                    "nombre": "Vitamin D",
                    "condicion": "DEFICIT_VIT_D",
                    "score": 1.0,
                    "tipo": "semilla_directa",
                },
                {
                    "component_id": "cmp_calcium",
                    "nombre": "Calcium",
                    "condicion": "soporte_funcional",
                    "score": 0.82,
                    "tipo": "candidato_gnn",
                },
            ],
            "packs_ranked": [
                {
                    "pack_id": "pack_test",
                    "rank": 1,
                    "component_ids": ["cmp_vit_d", "cmp_calcium"],
                    "component_names": ["Vitamin D", "Calcium"],
                    "score_final": 0.91,
                    "score_gnn": 0.88,
                    "score_coverage": 1.0,
                    "score_feedback": 0.7,
                    "feedback_count": 0,
                }
            ],
            "sinergias": [["Vitamin D", "Calcium", "soporte_salud_osea"]],
            "alertas": [],
            "combo_seguro": True,
            "mensaje": "OK",
        }

    app = create_app()
    app.state.models = {"pipeline_vitaminas": pipeline}

    status_code, body = asgi_request(app, "POST", "/api/v1/recommend", _survey_payload())

    assert status_code == 200
    assert body["recommendation_id"] == recommendation_id
    assert body["conditions"] == ["DEFICIT_VIT_D"]
    assert body["conditions_display"][0]["display_name"] == "Déficit de vitamina D"
    assert body["recommendations"][0]["name"] == "Vitamin D"
    assert body["recommendations"][0]["reason"] == "Relacionado con déficit de vitamina d."
    assert body["recommendations"][0]["icon_key"] == "sun"
    assert body["packs_ranked"][0]["title"] == "Vitamin D + Calcium"
    assert body["packs_ranked"][0]["components"][0]["display_name"] == "Vitamina D"
    assert body["sinergias"] == [
        {
            "component_a": "Vitamin D",
            "component_b": "Calcium",
            "type": "soporte_salud_osea",
        }
    ]
    assert body["alertas"] == []
    assert body["disclaimer"]

    with SessionLocal() as db:
        session = db.scalar(
            select(RecommendationSession).where(RecommendationSession.recommendation_id == recommendation_id)
        )
        if session is not None:
            db.delete(session)
            db.commit()


def test_recommend_endpoint_handles_extended_survey_context():
    recommendation_id = "rec_test_extended_survey"
    component_id = "COMP_94DFE28A9A5C"

    with SessionLocal() as db:
        existing = db.scalar(
            select(RecommendationSession).where(RecommendationSession.recommendation_id == recommendation_id)
        )
        if existing is not None:
            db.delete(existing)
            db.commit()

    def pipeline(payload, verbose=False):
        assert payload["tipo_dieta"] == "vegano"
        assert payload["dolor_muscular"] == 4
        assert payload["meta_energia"] == 1
        return {
            "recommendation_id": recommendation_id,
            "condiciones": ["DEFICIT_VIT_D"],
            "recomendaciones": [
                {
                    "component_id": component_id,
                    "nombre": "Vitamin D",
                    "condicion": "DEFICIT_VIT_D",
                    "score": 0.93,
                    "tipo": "semilla_directa",
                }
            ],
            "packs_ranked": [
                {
                    "pack_id": "pack_extended_survey",
                    "rank": 1,
                    "component_ids": [component_id],
                    "component_names": ["Vitamin D"],
                    "score_final": 0.91,
                    "score_gnn": 0.88,
                    "score_coverage": 1.0,
                    "score_feedback": 0.7,
                    "feedback_count": 0,
                }
            ],
            "sinergias": [],
            "alertas": [],
            "combo_seguro": True,
            "mensaje": "OK",
        }

    payload = {
        **_survey_payload(),
        "sexo": "femenino",
        "tipo_dieta": "vegano",
        "dolor_muscular": "frecuente",
        "dolor_articular": "nunca",
        "niebla_mental": "moderado",
        "caida_cabello": "nunca",
        "piel_seca": "leve",
        "unas_quebradizas": "nunca",
        "calambres": "nunca",
        "objetivos": ["energia", "salud_osea"],
        "toma_suplementos": "si",
        "suplementos_actuales": ["vitamina_d"],
        "restricciones": ["sin_gluten"],
        "condiciones_seguridad": ["medicacion_cronica"],
        "presupuesto": "bajo",
    }

    app = create_app()
    app.state.models = {"pipeline_vitaminas": pipeline}

    status_code, body = asgi_request(app, "POST", "/api/v1/recommend", payload)

    assert status_code == 200
    assert body["recommendation_id"] == recommendation_id
    assert body["profile_warnings"]
    assert body["safety_level"] == "medical_review_required"
    assert body["safety_actions"]
    assert any("Ya consumes suplementos" in warning for warning in body["profile_warnings"])
    assert any("interacciones" in warning.lower() for warning in body["profile_warnings"])
    assert any("Sin gluten" in warning for warning in body["profile_warnings"])
    assert body["recommendations"][0]["already_taking"] is True
    assert body["recommendations"][0]["safety_note"]
    assert body["commercial_recommendations_blocked"] is True
    assert body["recommendations"][0]["products"] == []
    assert body["packs_ranked"][0]["selected_products"] == []

    with SessionLocal() as db:
        session = db.scalar(
            select(RecommendationSession).where(RecommendationSession.recommendation_id == recommendation_id)
        )
        if session is not None:
            db.delete(session)
            db.commit()


def test_recommend_endpoint_ranks_products_when_profile_is_not_critical():
    recommendation_id = "rec_test_non_critical_products"
    component_id = "COMP_94DFE28A9A5C"

    with SessionLocal() as db:
        existing = db.scalar(
            select(RecommendationSession).where(RecommendationSession.recommendation_id == recommendation_id)
        )
        if existing is not None:
            db.delete(existing)
            db.commit()

    def pipeline(_payload, verbose=False):
        return {
            "recommendation_id": recommendation_id,
            "condiciones": ["DEFICIT_VIT_D"],
            "recomendaciones": [
                {
                    "component_id": component_id,
                    "nombre": "Vitamin D",
                    "condicion": "DEFICIT_VIT_D",
                    "score": 0.93,
                    "tipo": "semilla_directa",
                }
            ],
            "packs_ranked": [
                {
                    "pack_id": "pack_non_critical_products",
                    "rank": 1,
                    "component_ids": [component_id],
                    "component_names": ["Vitamin D"],
                    "score_final": 0.91,
                    "score_gnn": 0.88,
                    "score_coverage": 1.0,
                    "score_feedback": 0.7,
                    "feedback_count": 0,
                }
            ],
            "sinergias": [],
            "alertas": [],
            "combo_seguro": True,
            "mensaje": "OK",
        }

    payload = {
        **_survey_payload(),
        "sexo": "femenino",
        "tipo_dieta": "vegano",
        "objetivos": ["energia"],
        "toma_suplementos": "no",
        "suplementos_actuales": [],
        "restricciones": ["sin_gluten"],
        "condiciones_seguridad": ["ninguna"],
        "presupuesto": "bajo",
    }

    app = create_app()
    app.state.models = {"pipeline_vitaminas": pipeline}

    status_code, body = asgi_request(app, "POST", "/api/v1/recommend", payload)

    assert status_code == 200
    assert body["commercial_recommendations_blocked"] is False
    assert body["safety_level"] == "caution"
    assert body["recommendations"][0]["products"]
    assert body["packs_ranked"][0]["selected_products"]
    assert body["packs_ranked"][0]["selected_products"][0]["product_score"] is not None

    with SessionLocal() as db:
        session = db.scalar(
            select(RecommendationSession).where(RecommendationSession.recommendation_id == recommendation_id)
        )
        if session is not None:
            db.delete(session)
            db.commit()


def test_recommend_endpoint_persists_extended_survey_for_authenticated_user():
    recommendation_id = "rec_test_profile_persistence"
    email = "profile-persistence@suplematch.test"

    with SessionLocal() as db:
        existing_session = db.scalar(
            select(RecommendationSession).where(RecommendationSession.recommendation_id == recommendation_id)
        )
        if existing_session is not None:
            db.delete(existing_session)
        existing_user = db.scalar(select(User).where(User.email == email))
        if existing_user is not None:
            db.delete(existing_user)
        db.commit()
        user = UserRepository(db).create_user(email=email, password="ChangeMe123!", display_name="Profile Test")
        token = create_access_token(str(user.id), {"roles": ["user"]})

    def pipeline(_payload, verbose=False):
        return {
            "recommendation_id": recommendation_id,
            "condiciones": ["FATIGA"],
            "recomendaciones": [
                {
                    "component_id": "cmp_vit_d",
                    "nombre": "Vitamin D",
                    "condicion": "FATIGA",
                    "score": 0.86,
                    "tipo": "semilla_directa",
                }
            ],
            "packs_ranked": [],
            "sinergias": [],
            "alertas": [],
            "combo_seguro": True,
            "mensaje": "OK",
        }

    payload = {
        **_survey_payload(),
        "sexo": "femenino",
        "tipo_dieta": "vegetariano",
        "objetivos": ["energia"],
        "toma_suplementos": "si",
        "suplementos_actuales": ["magnesio", "omega_3"],
        "restricciones": ["alergia_pescado_mariscos", "sin_gluten"],
        "condiciones_seguridad": ["anticoagulantes"],
        "presupuesto": "bajo",
    }

    app = create_app()
    app.state.models = {"pipeline_vitaminas": pipeline}

    status_code, body = asgi_request(
        app,
        "POST",
        "/api/v1/recommend",
        payload,
        headers={"authorization": f"Bearer {token}"},
    )

    assert status_code == 200
    assert body["recommendation_id"] == recommendation_id

    with SessionLocal() as db:
        saved_user = db.scalar(select(User).where(User.email == email))
        assert saved_user is not None
        db.refresh(saved_user, attribute_names=["profile"])
        assert saved_user.profile is not None
        assert saved_user.profile.diet_type == "vegetariano"
        assert saved_user.profile.sex == "femenino"
        assert saved_user.profile.activity_level == payload["frecuencia_ejercicio"]
        assert saved_user.profile.health_goals["presupuesto"] == "bajo"
        assert saved_user.profile.health_goals["suplementos_actuales"] == ["magnesio", "omega_3"]
        assert saved_user.profile.allergies["restricciones"] == ["alergia_pescado_mariscos", "sin_gluten"]
        assert saved_user.profile.medical_warnings["condiciones_seguridad"] == ["anticoagulantes"]

        session = db.scalar(
            select(RecommendationSession).where(RecommendationSession.recommendation_id == recommendation_id)
        )
        if session is not None:
            db.delete(session)
        db.delete(saved_user)
        db.commit()
