from sqlalchemy import select

from app.db.models import RecommendationSession
from app.db.session import SessionLocal
from app.main import create_app
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
    assert body["packs_ranked"][0]["components"][0]["display_name"] == "Vitamin D"
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
