from app.schemas.encuesta import EncuestaInput
from app.schemas.recomendacion import RecommendationResponse
from app.core.errors import RECOMMENDATION_ERROR_DETAIL, RecommendationError
from app.services.recommendation_service import RecommendationService


def _encuesta() -> EncuestaInput:
    return EncuestaInput(
        edad_rango="31_50",
        horas_sueno="5_7h",
        frecuencia_ejercicio="1_2_semana",
        dieta="regular",
        fatiga="a_menudo",
        exposicion_solar="menos_15min",
        frecuencia_enfermedad="1_2_anio",
        estres="moderado",
        alcohol="ocasional",
    )


def test_recommendation_response_is_normalized_for_frontend_cards():
    def pipeline(_payload, verbose=False):
        return {
            "recommendation_id": "rec_123",
            "condiciones": ["DEFICIT_VIT_D", "DEFICIT_VIT_D", ""],
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
                    "pack_id": "pack_abc",
                    "rank": 1,
                    "component_ids": ["cmp_vit_d", "cmp_calcium"],
                    "component_names": ["Vitamin D", "Calcium"],
                    "score_final": 0.91,
                    "score_gnn": 0.88,
                    "score_coverage": 1.0,
                    "score_feedback": 0.7,
                    "feedback_count": 3,
                }
            ],
            "sinergias": [["Vitamin D", "Calcium", "soporte_salud_osea"]],
            "alertas": [("Iron", "Calcium", "INTERACCION_RIESGOSA")],
            "combo_seguro": False,
            "mensaje": "1 interacción(es) riesgosa(s).",
        }

    service = RecommendationService(models={"pipeline_vitaminas": pipeline})
    response = service.recommend(_encuesta())

    RecommendationResponse.model_validate(response)

    assert response["conditions"] == ["DEFICIT_VIT_D"]
    assert response["recommendations"] == [
        {
            "component_id": "cmp_vit_d",
            "name": "Vitamin D",
            "condition": "DEFICIT_VIT_D",
            "score": 1.0,
            "type": "semilla_directa",
        },
        {
            "component_id": "cmp_calcium",
            "name": "Calcium",
            "condition": "soporte_funcional",
            "score": 0.82,
            "type": "candidato_gnn",
        },
    ]
    assert response["packs_ranked"][0]["title"] == "Vitamin D + Calcium"
    assert response["packs_ranked"][0]["components"] == [
        {"component_id": "cmp_vit_d", "name": "Vitamin D"},
        {"component_id": "cmp_calcium", "name": "Calcium"},
    ]
    assert response["sinergias"] == [
        {
            "component_a": "Vitamin D",
            "component_b": "Calcium",
            "type": "soporte_salud_osea",
        }
    ]
    assert response["alertas"] == [
        {
            "component_a": "Iron",
            "component_b": "Calcium",
            "type": "INTERACCION_RIESGOSA",
        }
    ]
    assert response["disclaimer"]


def test_recommendation_fails_cleanly_when_model_is_missing():
    service = RecommendationService(models={"pipeline_vitaminas": None})

    try:
        service.recommend(_encuesta())
    except RecommendationError as exc:
        assert exc.detail == RECOMMENDATION_ERROR_DETAIL
    else:
        raise AssertionError("Expected RecommendationError")


def test_recommendation_fails_cleanly_when_pipeline_crashes():
    def pipeline(_payload, verbose=False):
        raise FileNotFoundError("modelo2_artifacts.pkl")

    service = RecommendationService(models={"pipeline_vitaminas": pipeline})

    try:
        service.recommend(_encuesta())
    except RecommendationError as exc:
        assert exc.detail == RECOMMENDATION_ERROR_DETAIL
    else:
        raise AssertionError("Expected RecommendationError")
