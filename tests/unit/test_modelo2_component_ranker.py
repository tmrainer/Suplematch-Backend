from __future__ import annotations

from app.domains.recommendations.servicio_recomendaciones import _attach_products_to_recommendations
from app.ml.runtime.feedback_reranker import rerank_packs
from app.ml.runtime.modelo2_inference import _component_enrichment, recomendar_suplementos


def test_modelo2_ranks_components_from_condition_probabilities_and_official_links() -> None:
    result = recomendar_suplementos(
        ["DEFICIT_VIT_D", "DEFICIT_B12", "RIESGO_OMEGA3_BAJO"],
        condition_scores={
            "DEFICIT_VIT_D": 0.82,
            "DEFICIT_B12": 0.65,
            "RIESGO_OMEGA3_BAJO": 0.71,
        },
    )

    direct = [
        item
        for item in result["recomendaciones"]
        if item.get("source") == "official_condition_component_link"
    ]

    assert result["model2_ranker_version"] == "component_ranker_v2"
    by_component = {item["component_id"]: item for item in direct}
    assert ["COMP_94DFE28A9A5C", "COMP_06B36D3A8FF3", "COMP_447F5E523CED"] == [
        component_id
        for component_id in ["COMP_94DFE28A9A5C", "COMP_06B36D3A8FF3", "COMP_447F5E523CED"]
        if component_id in by_component
    ]
    assert by_component["COMP_94DFE28A9A5C"]["nombre"] == "Vitamina D"
    assert by_component["COMP_06B36D3A8FF3"]["nombre"] == "Vitamina B12"
    assert by_component["COMP_447F5E523CED"]["nombre"] == "Omega 3"
    assert by_component["COMP_94DFE28A9A5C"]["score"] > by_component["COMP_06B36D3A8FF3"]["score"]
    assert by_component["COMP_06B36D3A8FF3"]["score"] > by_component["COMP_447F5E523CED"]["score"]
    assert direct[0]["evidence_strength"] == "high"
    assert direct[0]["evidence_type"] == "deficiency_replacement"
    assert direct[0]["recommendation_role"] == "primary"
    assert direct[0]["requires_lab"] == "preferred"
    assert direct[0]["source_quality"] == "official_fact_sheet"
    assert direct[0]["condition_probability"] == 0.82
    assert direct[0]["source_ids"]
    assert direct[0]["model2_stage"] == "evidence_validated"
    assert direct[0]["commercial_eligible"] is True


def test_modelo2_keeps_gnn_candidates_as_lower_weight_support() -> None:
    result = recomendar_suplementos(
        ["DEFICIT_VIT_D", "DEFICIT_B12", "RIESGO_OMEGA3_BAJO"],
        condition_scores={
            "DEFICIT_VIT_D": 0.90,
            "DEFICIT_B12": 0.72,
            "RIESGO_OMEGA3_BAJO": 0.70,
        },
    )

    direct = [
        item
        for item in result["recomendaciones"]
        if item.get("source") == "official_condition_component_link"
    ]
    support = [
        item
        for item in result["recomendaciones"]
        if item.get("source") == "gnn_functional_similarity"
    ]

    assert direct
    assert support
    assert all(item["tipo"] == "candidato_gnn" for item in support)
    assert max(item["score"] for item in support) < direct[0]["score"]
    assert all(item["model2_stage"] == "graph_support" for item in support)
    assert all(item["graph_similarity"] is not None for item in support)


def test_modelo2_penalizes_required_lab_and_exposes_evidence_factors() -> None:
    result = recomendar_suplementos(
        ["DEFICIT_HIERRO", "DEFICIT_B12"],
        condition_scores={
            "DEFICIT_HIERRO": 0.82,
            "DEFICIT_B12": 0.72,
        },
    )

    direct_by_component = {
        item["component_id"]: item
        for item in result["recomendaciones"]
        if item.get("source") == "official_condition_component_link"
    }

    iron = direct_by_component["COMP_B6A8F8958154"]
    b12 = direct_by_component["COMP_06B36D3A8FF3"]

    assert iron["component_id"] == "COMP_B6A8F8958154"
    assert iron["requires_lab"] == "required"
    assert iron["recommendation_role"] == "primary_with_lab"
    assert iron["risk_level"] == "moderate_high"
    assert iron["missing_data_penalty"] == 0.35
    assert iron["evidence_factors"]["lab_requirement_weight"] < b12["evidence_factors"]["lab_requirement_weight"]
    assert iron["score"] < b12["score"]


def test_modelo2_exposes_component_safety_profile() -> None:
    result = recomendar_suplementos(
        ["DEFICIT_HIERRO", "ESTRES_SUENO"],
        condition_scores={
            "DEFICIT_HIERRO": 0.82,
            "ESTRES_SUENO": 0.70,
        },
    )

    by_component = {
        item["nombre"]: item
        for item in result["recomendaciones"]
        if item.get("source") == "official_condition_component_link"
    }

    iron = by_component["Hierro"]
    melatonin = by_component["Melatonina"]

    assert iron["adult_upper_limit"] == "45"
    assert iron["upper_limit_unit"] == "mg/day"
    assert "moderate_high" == iron["risk_level"]
    assert "hemocromatosis" in iron["contraindications"]
    assert iron["component_safety_level"] == "high"
    assert iron["component_profile_source_ids"] == ["nih_ods_iron_hp"]

    assert melatonin["requires_lab"] == "no"
    assert melatonin["component_safety_level"] == "moderate"
    assert "embarazo_lactancia" in melatonin["contraindications"]
    assert melatonin["adult_upper_limit"] == ""


def test_modelo2_enriches_graph_alias_component_names() -> None:
    enrichment = _component_enrichment(None, "Vitamin C (ascorbic acid)", user_context=None)

    assert enrichment["component_profile_role"] == "core"
    assert enrichment["component_safety_level"] == "low"
    assert "vitamina c" in enrichment["component_lookup_candidates"]
    assert enrichment["claim_evidence"]


def test_modelo2_returns_contextual_life_stage_guidance_and_interactions() -> None:
    result = recomendar_suplementos(
        ["DEFICIT_HIERRO", "RIESGO_SALUD_OSEA"],
        condition_scores={
            "DEFICIT_HIERRO": 0.82,
            "RIESGO_SALUD_OSEA": 0.70,
        },
        user_context={
            "edad": 34,
            "sexo": "F",
            "condiciones_seguridad": ["anticoagulantes"],
        },
    )

    by_name = {
        item["nombre"]: item
        for item in result["recomendaciones"]
        if item.get("source") == "official_condition_component_link"
    }

    iron = by_name["Hierro"]
    vitamin_k = by_name["Vitamina K"]

    assert iron["life_stage_guidance"]
    assert iron["life_stage_guidance"][0]["reference_intake"] == "18"
    assert iron["life_stage_guidance"][0]["reference_unit"] == "mg/day"
    assert iron["claim_evidence"]
    assert iron["claim_evidence"][0]["claim_code"] == "supports_iron_status"

    assert vitamin_k["interaction_rules"]
    assert vitamin_k["interaction_rules"][0]["trigger_value"] == "anticoagulantes"
    assert vitamin_k["interaction_rules"][0]["severity"] == "high"


def test_modelo2_applies_allergy_restriction_interactions() -> None:
    result = recomendar_suplementos(
        ["RIESGO_OMEGA3_BAJO"],
        condition_scores={"RIESGO_OMEGA3_BAJO": 0.78},
        user_context={"restricciones_alergias": ["pescado_mariscos"]},
    )

    dha = next(
        item
        for item in result["recomendaciones"]
        if item.get("component_id") == "COMP_F71DD4665D9C"
    )

    assert dha["nombre"] == "DHA"
    assert dha["interaction_rules"]
    assert dha["interaction_rules"][0]["trigger_field"] == "restricciones_alergias"
    assert dha["commercial_eligible"] is False
    assert "pescado" in dha["commercial_block_reason"].lower()


def test_modelo2_marks_safety_context_as_non_commercial_context() -> None:
    result = recomendar_suplementos(
        ["SAFETY_RENAL"],
        condition_scores={"SAFETY_RENAL": 0.92},
        user_context={"condiciones_seguridad": ["enfermedad_renal"]},
    )

    safety_items = [
        item
        for item in result["recomendaciones"]
        if item.get("source") == "official_condition_component_link"
        and item.get("recommendation_role") == "safety_context"
    ]

    assert safety_items
    assert safety_items[0]["tipo"] == "contexto_seguridad"
    assert safety_items[0]["risk_level"] == "high"
    assert safety_items[0]["commercial_eligible"] is False
    assert safety_items[0]["commercial_block_reason"]


def test_safety_context_recommendations_do_not_attach_products() -> None:
    class FakeProductCatalog:
        def products_for_component(self, component_id):
            return [{"component_id": component_id, "commercial_name": "Producto demo"}]

    recommendations = [
        {
            "component_id": "COMP_BB2F708BF799",
            "recommendation_role": "safety_context",
        },
        {
            "component_id": "COMP_94DFE28A9A5C",
            "recommendation_role": "primary",
        },
    ]

    result = _attach_products_to_recommendations(recommendations, FakeProductCatalog())

    assert result[0]["products"] == []
    assert result[0]["commercial_recommendation_blocked"] is True
    assert result[1]["products"] == [
        {"component_id": "COMP_94DFE28A9A5C", "commercial_name": "Producto demo"}
    ]


def test_high_blocking_interactions_do_not_attach_products() -> None:
    class FakeProductCatalog:
        def products_for_component(self, component_id):
            return [{"component_id": component_id, "commercial_name": "Producto demo"}]

    recommendations = [
        {
            "component_id": "COMP_64DE5343502D",
            "recommendation_role": "supportive",
            "interaction_rules": [
                {
                    "severity": "high",
                    "action": "block_or_warn",
                    "message": "Vitamina K puede interferir con anticoagulantes.",
                }
            ],
        }
    ]

    result = _attach_products_to_recommendations(recommendations, FakeProductCatalog())

    assert result[0]["products"] == []
    assert result[0]["commercial_recommendation_blocked"] is True
    assert result[0]["commercial_block_reason"] == "Vitamina K puede interferir con anticoagulantes."


def test_warn_or_block_interactions_do_not_attach_products() -> None:
    class FakeProductCatalog:
        def products_for_component(self, component_id):
            return [{"component_id": component_id, "commercial_name": "Producto demo"}]

    recommendations = [
        {
            "component_id": "COMP_64DE5343502D",
            "recommendation_role": "supportive",
            "interaction_rules": [
                {
                    "severity": "high",
                    "action": "warn_or_block",
                    "message": "Vitamina K requiere revisión profesional.",
                }
            ],
        }
    ]

    result = _attach_products_to_recommendations(recommendations, FakeProductCatalog())

    assert result[0]["products"] == []
    assert result[0]["commercial_recommendation_blocked"] is True
    assert result[0]["commercial_block_reason"] == "Vitamina K requiere revisión profesional."


def test_modelo2_blocks_creatine_commercialization_for_renal_context() -> None:
    result = recomendar_suplementos(
        ["RENDIMIENTO_DEPORTIVO"],
        condition_scores={"RENDIMIENTO_DEPORTIVO": 0.76},
        user_context={"condiciones_seguridad": ["enfermedad_renal"]},
    )

    creatine = next(
        item
        for item in result["recomendaciones"]
        if item.get("component_id") == "COMP_7B47CDB437E8"
    )

    assert creatine["nombre"] == "Creatina"
    assert creatine["commercial_eligible"] is False
    assert "renal" in creatine["commercial_block_reason"].lower()
    assert creatine["interaction_rules"][0]["action"] == "block_commercial"


def test_modelo2_marks_wellness_only_recommendations_as_context_not_commercial() -> None:
    result = recomendar_suplementos(
        ["ESTRES_SUENO"],
        condition_scores={"ESTRES_SUENO": 0.91},
    )

    assert result["recomendaciones"]
    assert all(item["commercial_eligible"] is False for item in result["recomendaciones"])
    assert any(
        "prioridad blanda" in str(item.get("commercial_block_reason", "")).lower()
        for item in result["recomendaciones"]
        if item.get("condicion") == "ESTRES_SUENO"
    )


def test_modelo2_prefers_nutrition_condition_when_same_component_also_supports_wellness() -> None:
    result = recomendar_suplementos(
        ["DEFICIT_MAGNESIO", "ESTRES_SUENO"],
        condition_scores={"DEFICIT_MAGNESIO": 0.72, "ESTRES_SUENO": 0.91},
    )

    magnesium = next(item for item in result["recomendaciones"] if item["nombre"] == "Magnesio")

    assert magnesium["condicion"] == "DEFICIT_MAGNESIO"
    assert magnesium["commercial_eligible"] is True


def test_reranker_excludes_safety_and_blocked_components_from_packs() -> None:
    recommendations = [
        {
            "component_id": "COMP_7B47CDB437E8",
            "nombre": "Creatina",
            "condicion": "RENDIMIENTO_DEPORTIVO",
            "score": 0.9,
            "commercial_eligible": False,
        },
        {
            "component_id": "COMP_BB2F708BF799",
            "nombre": "Potasio",
            "condicion": "SAFETY_RENAL",
            "score": 0.8,
            "recommendation_role": "safety_context",
        },
        {
            "component_id": "COMP_927AAC8EA873",
            "nombre": "Proteína",
            "condicion": "RENDIMIENTO_DEPORTIVO",
            "score": 0.7,
            "commercial_eligible": True,
        },
    ]

    packs = rerank_packs(recommendations, conditions=["RENDIMIENTO_DEPORTIVO", "SAFETY_RENAL"])

    assert packs
    assert packs[0]["component_ids"] == ["COMP_927AAC8EA873"]


def test_reranker_excludes_warn_or_block_interactions_from_packs() -> None:
    recommendations = [
        {
            "component_id": "COMP_64DE5343502D",
            "nombre": "Vitamina K",
            "condicion": "RIESGO_SALUD_OSEA",
            "score": 0.8,
            "commercial_eligible": True,
            "interaction_rules": [
                {
                    "severity": "high",
                    "action": "warn_or_block",
                    "message": "Revisión profesional requerida.",
                }
            ],
        },
        {
            "component_id": "COMP_94DFE28A9A5C",
            "nombre": "Vitamina D",
            "condicion": "RIESGO_SALUD_OSEA",
            "score": 0.7,
            "commercial_eligible": True,
        },
    ]

    packs = rerank_packs(recommendations, conditions=["RIESGO_SALUD_OSEA"])

    assert packs
    assert packs[0]["component_ids"] == ["COMP_94DFE28A9A5C"]


def test_modelo2_returns_structured_graph_relations() -> None:
    result = recomendar_suplementos(
        ["DEFICIT_VIT_D", "RIESGO_SALUD_OSEA"],
        condition_scores={"DEFICIT_VIT_D": 0.88, "RIESGO_SALUD_OSEA": 0.80},
    )

    if result["sinergias"]:
        synergy = result["sinergias"][0]
        assert {"component_a", "component_b", "component_a_id", "component_b_id", "type"}.issubset(synergy)
        assert synergy["model2_stage"] == "graph_relationship"
