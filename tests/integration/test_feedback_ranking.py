"""El feedback guardado en Postgres cambia el orden de los packs en la siguiente recomendacion.

Cierra el ciclo completo: /recommend -> /feedback -> /recommend. La parte unitaria (recompensa, score bayesiano,
contexto) esta en tests/unit/test_feedback_reward_context.py; aqui se prueba que la ruta real lo aplica.
"""

from __future__ import annotations

from itertools import count
from uuid import uuid4

from sqlalchemy import delete, select

from app.db.models import RecommendationFeedback, RecommendationSession
from app.domains.feedback.contexto import MIN_FEEDBACK_TO_RERANK
from app.db.session import SessionLocal
from app.main import create_app
from tests.integration.test_health import asgi_request
from tests.integration.test_recommend_endpoint import _auth_headers, _survey_payload, needs_models

MAX_VOTES = 15


def _assert_moves_only_after_minimum(scores: list[float], direction: int) -> None:
    """Sin cambio hasta MIN_FEEDBACK_TO_RERANK votos; desde ahi, monotono en `direction` (+1 sube, -1 baja)."""
    before_minimum = scores[:MIN_FEEDBACK_TO_RERANK]
    assert len(set(before_minimum)) == 1, f"el feedback se movio antes de {MIN_FEEDBACK_TO_RERANK} votos: {scores}"
    after = scores[MIN_FEEDBACK_TO_RERANK - 1 :]
    assert all((b - a) * direction > 0 for a, b in zip(after, after[1:])), scores


def _stub_pipeline(prefix: str, pack_a: str, pack_b: str):
    """Pipeline falso con dos packs de mismos componentes: solo los separa score_gnn (A apenas por encima)."""
    ids = count()

    def pipeline(_payload, verbose=False):
        def pack(pack_id: str, score_gnn: float) -> dict:
            return {
                "pack_id": pack_id,
                "component_ids": ["cmp_vit_d", "cmp_calcium"],
                "component_names": ["Vitamin D", "Calcium"],
                "score_gnn": score_gnn,
                "score_coverage": 1.0,
            }

        return {
            "recommendation_id": f"{prefix}_{next(ids)}",
            "condiciones": ["DEFICIT_VIT_D"],
            "recomendaciones": [
                {"component_id": "cmp_vit_d", "nombre": "Vitamin D", "condicion": "DEFICIT_VIT_D", "score": 1.0, "tipo": "semilla_directa"},
            ],
            "packs_ranked": [pack(pack_a, 0.80), pack(pack_b, 0.78)],
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


def _pack(body: dict, pack_id: str) -> dict:
    return next(pack for pack in body["packs_ranked"] if pack["pack_id"] == pack_id)


def _vote(app, body: dict, pack_id: str, rating: int) -> None:
    payload = {
        "recommendation_id": body["recommendation_id"],
        "pack_id": pack_id,
        "component_ids": _pack(body, pack_id).get("component_ids", []),
        "rating": rating,
        "conditions": body.get("conditions", []),
    }
    status_code, response = asgi_request(app, "POST", "/api/v1/feedback", payload)
    assert status_code == 200, response


def _cleanup(recommendation_ids: list[str]) -> None:
    with SessionLocal() as db:
        session_ids = list(
            db.scalars(select(RecommendationSession.id).where(RecommendationSession.recommendation_id.in_(recommendation_ids)))
        )
        if session_ids:
            db.execute(delete(RecommendationFeedback).where(RecommendationFeedback.recommendation_session_id.in_(session_ids)))
            db.execute(delete(RecommendationSession).where(RecommendationSession.id.in_(session_ids)))
        db.commit()


def _vote_until_top_changes(app, headers, rating: int, target_rank: int) -> tuple[int, list[float], dict]:
    """Vota `rating` al pack en `target_rank` de cada nueva recomendacion hasta que deje ese puesto.

    Devuelve (votos, score_feedback del pack tras cada voto, ultima respuesta).
    """
    body = _recommend(app, headers)
    target = body["packs_ranked"][target_rank - 1]["pack_id"]
    scores = [_pack(body, target)["score_feedback"]]
    recommendation_ids = [body["recommendation_id"]]
    try:
        for votes in range(1, MAX_VOTES + 1):
            _vote(app, body, target, rating)
            body = _recommend(app, headers)
            recommendation_ids.append(body["recommendation_id"])
            scores.append(_pack(body, target)["score_feedback"])
            if _pack(body, target)["rank"] != target_rank:
                return votes, scores, body
        return MAX_VOTES + 1, scores, body
    finally:
        _cleanup(recommendation_ids)


def test_negative_feedback_moves_pack_down_and_positive_moves_it_up():
    suffix = uuid4().hex[:8]
    pack_a, pack_b = f"pack_rank_a_{suffix}", f"pack_rank_b_{suffix}"
    app = create_app()
    app.state.models = {"pipeline_vitaminas": _stub_pipeline(f"rec_rank_{suffix}", pack_a, pack_b)}
    headers = _auth_headers("feedback-ranking@suplematch.test")

    baseline = _recommend(app, headers)
    _cleanup([baseline["recommendation_id"]])
    assert [pack["pack_id"] for pack in baseline["packs_ranked"]] == [pack_a, pack_b]
    assert _pack(baseline, pack_a)["score_feedback"] == _pack(baseline, pack_b)["score_feedback"]

    # Negativo al primero: baja su score_feedback y pierde el primer puesto.
    votes, scores, body = _vote_until_top_changes(app, headers, rating=1, target_rank=1)
    assert MIN_FEEDBACK_TO_RERANK <= votes <= MAX_VOTES, f"votos={votes}, score_feedback={scores}"
    _assert_moves_only_after_minimum(scores, direction=-1)
    assert body["packs_ranked"][0]["pack_id"] == pack_b

    # Positivo al segundo: sube su score_feedback y gana el primer puesto.
    votes, scores, body = _vote_until_top_changes(app, headers, rating=5, target_rank=2)
    assert MIN_FEEDBACK_TO_RERANK <= votes <= MAX_VOTES, f"votos={votes}, score_feedback={scores}"
    _assert_moves_only_after_minimum(scores, direction=+1)
    assert body["packs_ranked"][0]["pack_id"] == pack_b


@needs_models
def test_negative_feedback_reorders_packs_with_real_models():
    """Con los modelos reales: votos negativos al pack principal lo sacan del primer puesto."""
    from app.ml.model_loader import load_all_models

    app = create_app()
    app.state.models = load_all_models()
    headers = _auth_headers("feedback-ranking-real@suplematch.test")

    baseline = _recommend(app, headers)
    _cleanup([baseline["recommendation_id"]])
    assert len(baseline["packs_ranked"]) >= 2, "el perfil de prueba necesita al menos dos packs"

    votes, scores, body = _vote_until_top_changes(app, headers, rating=1, target_rank=1)
    assert MIN_FEEDBACK_TO_RERANK <= votes <= MAX_VOTES, f"votos={votes}, score_feedback={scores}"
    _assert_moves_only_after_minimum(scores, direction=-1)
    print(f"votos negativos necesarios para cambiar el primer pack: {votes}; score_feedback {scores}")
