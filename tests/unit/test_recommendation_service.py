from app.domains.survey.esquemas_encuesta import EncuestaInput
from app.domains.recommendations.esquemas import RecommendationResponse
from app.core.errors import RECOMMENDATION_ERROR_DETAIL, RecommendationError
from app.domains.recommendations.servicio_recomendaciones import RecommendationService


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
    assert response["conditions_display"][0]["display_name"] == "Déficit de vitamina D"
    assert response["recommendations"][0]["name"] == "Vitamin D"
    assert response["recommendations"][0]["display_name"] == "Vitamina D"
    assert response["recommendations"][0]["condition_display"] == "Déficit de vitamina D"
    assert response["recommendations"][0]["reason"] == "Relacionado con déficit de vitamina d."
    assert response["recommendations"][0]["dosage_hint"]
    assert response["recommendations"][0]["priority"] == "principal"
    assert response["recommendations"][1]["type_display"] == "Soporte complementario"
    assert response["packs_ranked"][0]["title"] == "Vitamin D + Calcium"
    assert response["packs_ranked"][0]["components"] == [
        {
            "component_id": "cmp_vit_d",
            "name": "Vitamin D",
            "display_name": "Vitamina D",
            "icon_key": "sun",
        },
        {
            "component_id": "cmp_calcium",
            "name": "Calcium",
            "display_name": "Calcio",
            "icon_key": "bone",
        },
    ]
    assert response["packs_ranked"][0]["subtitle"] == "2 suplemento(s) priorizados para tu perfil"
    assert response["packs_ranked"][0]["cta_label"] == "Ver detalle del pack"
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
    assert response["condition_results"][0]["code"] == "DEFICIT_VIT_D"
    assert response["condition_results"][0]["kind"] == "nutrition_risk"
    assert response["disclaimer"]


def test_recommendation_response_separates_risks_wellness_and_safety():
    def pipeline(_payload, verbose=False):
        return {
            "recommendation_id": "rec_taxonomy",
            "condiciones": ["DEFICIT_B12", "PROBLEMAS_SUENO", "SAFETY_RENAL"],
            "condition_scores": {
                "DEFICIT_B12": 0.77,
                "PROBLEMAS_SUENO": 0.82,
                "SAFETY_RENAL": 0.91,
            },
            "recomendaciones": [],
            "packs_ranked": [],
            "sinergias": [],
            "alertas": [],
            "combo_seguro": True,
            "mensaje": "OK",
        }

    service = RecommendationService(models={"pipeline_vitaminas": pipeline})
    response = service.recommend(_encuesta())

    RecommendationResponse.model_validate(response)

    assert response["condition_results"][0] | {
        "primary_signal_group": "unknown",
        "signal_strength": "baja",
        "signal_groups": {},
        "drivers": [],
        "missing_data": [],
        "model_probability": None,
        "rule_score": None,
        "calibrated_by_rules": False,
    } == response["condition_results"][0]
    assert {
        key: response["condition_results"][0][key]
        for key in (
            "code",
            "display_name",
            "kind",
            "probability",
            "level",
            "evidence_group",
            "confidence_label",
            "recommendation_strength",
            "benchmark_status",
            "validation_source",
            "allowed_for_commercial_recommendation",
            "requires_disclaimer",
            "explanation",
        )
    } == {
        "code": "DEFICIT_B12",
        "display_name": "Déficit de vitamina B12",
        "kind": "nutrition_risk",
        "probability": 0.77,
        "level": "Alta prioridad",
        "evidence_group": "diet_or_lab",
        "confidence_label": "alta",
        "recommendation_strength": "alta",
        "benchmark_status": "evaluated_with_nhanes_when_data_available",
        "validation_source": "nhanes_multi_cycle_diet_lab_rules",
        "allowed_for_commercial_recommendation": True,
        "requires_disclaimer": True,
        "explanation": "Riesgo estimado por señales estructuradas de encuesta, dieta o laboratorio cuando están disponibles.",
    }
    assert response["wellness_priorities"][0]["code"] == "ESTRES_SUENO"
    assert response["wellness_priorities"][0]["kind"] == "wellness_priority"
    assert response["wellness_priorities"][0]["benchmark_status"] == "not_evaluable_with_nhanes_use_survey_golden_cases"
    assert response["wellness_priorities"][0]["recommendation_strength"] == "no_convertir"
    assert response["wellness_priorities"][0]["allowed_for_commercial_recommendation"] is False
    assert response["safety_flags"][0]["code"] == "SAFETY_RENAL"
    assert response["safety_flags"][0]["allowed_for_commercial_recommendation"] is False


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


def test_recommendation_includes_approved_products_for_real_component_ids():
    def pipeline(_payload, verbose=False):
        return {
            "recommendation_id": "rec_products",
            "condiciones": ["DEFICIT_VIT_D"],
            "recomendaciones": [
                {
                    "component_id": "COMP_94DFE28A9A5C",
                    "nombre": "Vitamin D",
                    "condicion": "DEFICIT_VIT_D",
                    "score": 1.0,
                    "tipo": "semilla_directa",
                }
            ],
            "packs_ranked": [
                {
                    "pack_id": "pack_products",
                    "rank": 1,
                    "component_ids": ["COMP_94DFE28A9A5C"],
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

    service = RecommendationService(models={"pipeline_vitaminas": pipeline})
    response = service.recommend(_encuesta())

    RecommendationResponse.model_validate(response)

    assert response["recommendations"][0]["products"]
    assert response["recommendations"][0]["products"][0]["regulatory_status"] == "digemid_match"
    assert response["packs_ranked"][0]["selected_products"]
    assert response["packs_ranked"][0]["selected_products"][0]["component_id"] == "COMP_94DFE28A9A5C"
