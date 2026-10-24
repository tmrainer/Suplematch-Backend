"""Estrellas por suplemento: /recommend -> /feedback con item_ratings -> /recommend.

Prueba que la condicion la pone el servidor, que solo se aceptan suplementos mostrados, que reenviar no suma votos
y que el orden cambia solo dentro del mismo nivel despues de MIN_ITEM_FEEDBACK_TO_RERANK votos.
"""

from __future__ import annotations

from itertools import count
from uuid import uuid4

from sqlalchemy import select

from app.db.models import RecommendationItemFeedback
from app.db.session import SessionLocal
from app.domains.feedback.contexto import MIN_ITEM_FEEDBACK_TO_RERANK
from app.main import create_app
from tests.integration.test_feedback_ranking import _cleanup
from tests.integration.test_health import asgi_request
from tests.integration.test_recommend_endpoint import _auth_headers, _survey_payload


def _stub_pipeline(prefix: str, suffix: str):
    ids = count()

    def rec(component: str, name: str, tipo: str, grade: str) -> dict:
        return {
            "component_id": f"cmp_{component}_{suffix}",
            "nombre": name,
            "condicion": "DEFICIT_VIT_D",
            "score": 0.9,
            "tipo": tipo,
            "evidence_grade": grade,
        }

    def pipeline(_payload, verbose=False):
        return {
            "recommendation_id": f"{prefix}_{next(ids)}",
            "condiciones": ["DEFICIT_VIT_D"],
            "recomendaciones": [
                rec("vit_d", "Vitamin D", "semilla_directa", "moderate"),
                rec("calcium", "Calcium", "candidato_gnn", "moderate"),
                rec("vit_k", "Vitamin K", "candidato_gnn", "moderate"),
            ],
            "packs_ranked": [],
            "sinergias": [],
            "alertas": [],
            "combo_seguro": True,
            "mensaje": "OK",
        }

    return pipeline


def _recommend(app, headers) -> dict:
    status_code, body = asgi_request(app, "POST", "/api/v1/recommend", _survey_payload(), headers=headers)
    assert status_code == 200, body
    return body


def _rate(app, body: dict, ratings: dict[str, int]) -> dict:
    payload = {
        "recommendation_id": body["recommendation_id"],
        "rating": 3,
        "conditions": body.get("conditions", []),
        "item_ratings": [{"component_id": component_id, "rating": stars} for component_id, stars in ratings.items()],
    }
    status_code, response = asgi_request(app, "POST", "/api/v1/feedback", payload)
    assert status_code == 200, response
    return response


def _order(body: dict) -> list[str]:
    return [item["component_id"] for item in body["recommendations"]]


def test_item_ratings_are_stored_with_the_server_side_condition_and_only_for_shown_supplements():
    suffix = uuid4().hex[:8]
    app = create_app()
    app.state.models = {"pipeline_vitaminas": _stub_pipeline(f"rec_item_{suffix}", suffix)}
    body = _recommend(app, _auth_headers("item-feedback@suplematch.test"))
    calcium = f"cmp_calcium_{suffix}"
    try:
        response = _rate(app, body, {calcium: 4, "cmp_no_mostrado": 5})
        assert response["item_ratings_saved"] == 1
        assert response["item_ratings_ignored"] == ["cmp_no_mostrado"]

        again = _rate(app, body, {calcium: 2})  # reenviar reemplaza, no suma
        assert again["status"] == "updated" and again["item_ratings_saved"] == 1
        with SessionLocal() as db:
            rows = db.scalars(select(RecommendationItemFeedback).where(RecommendationItemFeedback.component_id == calcium)).all()
            assert [(row.rating, row.condition_code, row.context_key) for row in rows] == [(2, "DEFICIT_VIT_D", f"{calcium}|DEFICIT_VIT_D")]
    finally:
        _cleanup([body["recommendation_id"]])


def test_low_stars_move_a_supplement_down_only_within_its_tier_after_enough_votes():
    suffix = uuid4().hex[:8]
    app = create_app()
    app.state.models = {"pipeline_vitaminas": _stub_pipeline(f"rec_item_rank_{suffix}", suffix)}
    headers = _auth_headers("item-feedback-rank@suplematch.test")
    vit_d, calcium, vit_k = (f"cmp_{name}_{suffix}" for name in ("vit_d", "calcium", "vit_k"))

    body = _recommend(app, headers)
    created = [body["recommendation_id"]]
    try:
        assert _order(body) == [vit_d, calcium, vit_k]
        # La respuesta omite los None: sin votos no hay `stars`.
        assert body["recommendations"][1]["user_rating"] == {"count": 0, "score": 0.7, "source": "none", "context_count": 0, "total_count": 0}
        for vote in range(1, MIN_ITEM_FEEDBACK_TO_RERANK + 1):
            # 1 estrella al calcio y al suplemento principal: el principal no puede bajar de grupo.
            _rate(app, body, {calcium: 1, vit_d: 1})
            body = _recommend(app, headers)
            created.append(body["recommendation_id"])
            if vote < MIN_ITEM_FEEDBACK_TO_RERANK:
                assert _order(body) == [vit_d, calcium, vit_k], f"se movio con {vote} votos"

        assert _order(body) == [vit_d, vit_k, calcium]
        rated = next(item for item in body["recommendations"] if item["component_id"] == calcium)["user_rating"]
        assert rated["stars"] == 1.0 and rated["count"] == MIN_ITEM_FEEDBACK_TO_RERANK and rated["source"] == "context"
        assert rated["score"] < 0.7
    finally:
        _cleanup(created)
