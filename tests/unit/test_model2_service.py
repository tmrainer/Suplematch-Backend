"""Smoke del Modelo 2 (ranker de componentes). Se omite si el artefacto no esta en MODEL_DIR."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from app.core.config import settings

# Requiere el artefacto del Modelo 2 y torch (para deserializar los embeddings). En CI limpio se omite.
needs_model2 = pytest.mark.skipif(
    not (Path(settings.MODEL_DIR) / "modelo2_artifacts.pkl").exists() or importlib.util.find_spec("torch") is None,
    reason="modelo2_artifacts.pkl o torch no disponibles (artefacto no versionado)",
)

pytestmark = needs_model2


def test_ranker_returns_components_for_vitamin_d_deficit() -> None:
    from app.ml.runtime.modelo2_inference import recomendar_suplementos

    result = recomendar_suplementos(["DEFICIT_VIT_D"], {"DEFICIT_VIT_D": 0.8}, user_context={})

    recs = result.get("recomendaciones") or result.get("recommendations") or []
    assert recs, result.keys()
    names = " ".join(str(r.get("nombre") or r.get("name") or "").lower() for r in recs)
    assert "vitamin" in names and "d" in names


def test_pregnancy_context_blocks_high_dose_vitamin_a() -> None:
    from app.ml.runtime.modelo2_inference import recomendar_suplementos

    result = recomendar_suplementos(
        ["DEFICIT_ZINC"],
        {"DEFICIT_ZINC": 0.7},
        user_context={"condiciones_seguridad": ["embarazo_lactancia"]},
    )
    recs = result.get("recomendaciones") or result.get("recommendations") or []
    vitamin_a = [r for r in recs if "vitamina a" in str(r.get("nombre") or r.get("name") or "").lower()]
    # Si aparece vitamina A (p. ej. como candidato GNN), la regla de interaccion embarazo_lactancia debe
    # bloquearla comercialmente. Antes la regla usaba el codigo 'embarazo' y nunca se activaba.
    for item in vitamin_a:
        assert item.get("commercial_eligible") is False, item
        assert any(rule.get("trigger_value") == "embarazo_lactancia" for rule in item.get("interaction_rules") or []), item


@pytest.mark.parametrize(
    "conditions,scores",
    [
        (["DEFICIT_VIT_D", "DEFICIT_CALCIO"], {"DEFICIT_VIT_D": 0.8, "DEFICIT_CALCIO": 0.7}),
        (["BAJA_INMUNIDAD", "DEFICIT_ZINC"], {"BAJA_INMUNIDAD": 0.7, "DEFICIT_ZINC": 0.7}),
        (["DEFICIT_B12", "DEFICIT_HIERRO"], {"DEFICIT_B12": 0.7, "DEFICIT_HIERRO": 0.7}),
    ],
)
def test_no_two_recommendations_share_a_canonical_component(conditions, scores) -> None:
    """Nodos equivalentes del grafo ("Vitamin D", "Vitamin D (unspecified)") no deben salir como dos componentes."""
    from app.ml.runtime.modelo2_inference import canonical_graph_id, recomendar_suplementos

    result = recomendar_suplementos(conditions, scores, user_context={})
    recs = result.get("recomendaciones") or []
    assert recs
    canonical_ids = [canonical_graph_id(r["component_id"]) for r in recs]
    assert len(canonical_ids) == len(set(canonical_ids)), canonical_ids
    for item in recs:
        if item.get("tipo") == "candidato_gnn":
            assert item["graph_node_canonical_id"] == canonical_graph_id(item["component_id"])
