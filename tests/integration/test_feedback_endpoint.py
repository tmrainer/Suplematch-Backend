from uuid import UUID

from app.main import create_app
from app.db.models import RecommendationFeedback, RecommendationSession
from app.db.session import SessionLocal
from tests.integration.test_health import asgi_request


def _ensure_recommendation_session(recommendation_id: str) -> None:
    with SessionLocal() as db:
        existing = db.query(RecommendationSession).filter_by(recommendation_id=recommendation_id).first()
        if existing is None:
            db.add(RecommendationSession(recommendation_id=recommendation_id, conditions_json={}, input_payload_json={}))
            db.commit()


def test_feedback_for_unknown_recommendation_is_rejected():
    app = create_app()
    status_code, _body = asgi_request(
        app,
        "POST",
        "/api/v1/feedback",
        {"recommendation_id": "rec_does_not_exist", "rating": 5},
    )
    assert status_code == 404


def test_feedback_endpoint_persists_event_in_postgres():
    app = create_app()
    _ensure_recommendation_session("rec_feedback_test")
    payload = {
        "recommendation_id": "rec_feedback_test",
        "pack_id": "pack_feedback_test",
        "component_ids": ["cmp_vit_d", "cmp_calcium"],
        "selected_product_ids": ["11111111-1111-1111-1111-111111111111"],
        "chosen_product_id": "11111111-1111-1111-1111-111111111111",
        "product_context": {
            "selected_products": [
                {
                    "product_id": "11111111-1111-1111-1111-111111111111",
                    "commercial_name": "Vitamina D Test",
                    "commercial_score": 0.91,
                    "selection_reasons": ["Elegido por mejor precio"],
                }
            ]
        },
        "rating": 5,
        "conditions": ["DEFICIT_VIT_D"],
        "comment": "Me sirvió para la demo",
    }

    status_code, body = asgi_request(app, "POST", "/api/v1/feedback", payload)

    assert status_code == 200
    assert body["status"] == "saved"
    assert body["recommendation_id"] == "rec_feedback_test"
    assert body["rating"] == 5

    with SessionLocal() as db:
        feedback = db.get(RecommendationFeedback, UUID(body["feedback_id"]))
        assert feedback is not None
        assert feedback.pack_key == "pack_feedback_test"
        assert feedback.component_ids_json == ["cmp_vit_d", "cmp_calcium"]
        assert feedback.selected_product_ids_json == ["11111111-1111-1111-1111-111111111111"]
        assert feedback.chosen_product_id is None
        assert feedback.product_context_json["selected_products"][0]["commercial_score"] == 0.91
        assert feedback.rating == 5
        db.delete(feedback)
        db.commit()

    # Segundo envio del mismo pack: actualiza, no duplica.
    payload["rating"] = 3
    status_code, body = asgi_request(app, "POST", "/api/v1/feedback", payload)
    assert status_code == 200
    status_code, body2 = asgi_request(app, "POST", "/api/v1/feedback", payload)
    assert status_code == 200
    assert body2["status"] == "updated"
    assert body2["feedback_id"] == body["feedback_id"]
    with SessionLocal() as db:
        feedback = db.get(RecommendationFeedback, UUID(body["feedback_id"]))
        db.delete(feedback)
        db.commit()


def test_feedback_events_batch_persists_and_dedupes_impressions():
    from app.db.models import RecommendationEvent

    app = create_app()
    _ensure_recommendation_session("rec_events_test")

    status_code, body = asgi_request(
        app,
        "POST",
        "/api/v1/feedback/events",
        {"events": [{"recommendation_id": "rec_does_not_exist", "event_type": "click", "pack_key": "pack_x"}]},
    )
    assert status_code == 404

    payload = {
        "anonymous_session_id": "ses_events_test",
        "events": [
            {"recommendation_id": "rec_events_test", "event_type": "impression", "pack_key": "pack_evt_a", "position": 1,
             "conditions": ["DEFICIT_VIT_D", "ESTRES_CRONICO"]},
            {"recommendation_id": "rec_events_test", "event_type": "impression", "pack_key": "pack_evt_a", "position": 1,
             "conditions": ["DEFICIT_VIT_D", "ESTRES_CRONICO"]},
            {"recommendation_id": "rec_events_test", "event_type": "impression", "pack_key": "pack_evt_b", "position": 2},
            {"recommendation_id": "rec_events_test", "event_type": "click", "pack_key": "pack_evt_a", "position": 1,
             "payload": {"ui": "card"}},
        ],
    }
    status_code, body = asgi_request(app, "POST", "/api/v1/feedback/events", payload)
    assert status_code == 200
    assert body["status"] == "saved"
    assert body["accepted"] == 3
    assert body["deduplicated"] == 1
    assert len(body["event_ids"]) == 3

    # Reenviar el mismo lote: las impresiones ya existen, solo pasa el click.
    status_code, body2 = asgi_request(app, "POST", "/api/v1/feedback/events", payload)
    assert status_code == 200
    assert body2["accepted"] == 1
    assert body2["deduplicated"] == 3

    with SessionLocal() as db:
        rows = [db.get(RecommendationEvent, UUID(event_id)) for event_id in body["event_ids"] + body2["event_ids"]]
        assert all(row is not None for row in rows)
        impression = next(row for row in rows if row.event_type == "impression" and row.pack_key == "pack_evt_a")
        assert impression.position == 1
        assert impression.context_key == "pack_evt_a|DEFICIT_VIT_D+ESTRES_CRONICO"
        assert impression.anonymous_session_id == "ses_events_test"
        assert impression.recommendation_session_id is not None
        for row in rows:
            db.delete(row)
        db.commit()


def test_feedback_with_outcomes_stores_reward_and_context_key():
    app = create_app()
    _ensure_recommendation_session("rec_feedback_reward_test")
    payload = {
        "recommendation_id": "rec_feedback_reward_test",
        "pack_id": "pack_reward_test",
        "rating": 4,
        "conditions": ["ESTRES_CRONICO", "DEFICIT_VIT_D", "SALUDABLE"],
        "purchased": True,
        "still_taking_30d": True,
        "perceived_benefit": "leve",
    }
    status_code, body = asgi_request(app, "POST", "/api/v1/feedback", payload)
    assert status_code == 200
    assert body["context_key"] == "pack_reward_test|DEFICIT_VIT_D+ESTRES_CRONICO"
    assert abs(body["reward"] - (0.4 * 0.75 + 0.2 + 0.3 + 0.05)) < 1e-6

    with SessionLocal() as db:
        feedback = db.get(RecommendationFeedback, UUID(body["feedback_id"]))
        assert feedback.context_key == "pack_reward_test|DEFICIT_VIT_D+ESTRES_CRONICO"
        assert feedback.outcome_json["purchased"] is True
        assert abs(feedback.outcome_json["reward"] - body["reward"]) < 1e-4
        db.delete(feedback)
        db.commit()
