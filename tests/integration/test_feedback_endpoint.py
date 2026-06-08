from uuid import UUID

from app.main import create_app
from app.db.models import RecommendationFeedback
from app.db.session import SessionLocal
from tests.integration.test_health import asgi_request


def test_feedback_endpoint_persists_event_in_postgres():
    app = create_app()
    payload = {
        "recommendation_id": "rec_feedback_test",
        "pack_id": "pack_feedback_test",
        "component_ids": ["cmp_vit_d", "cmp_calcium"],
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
        assert feedback.rating == 5
        db.delete(feedback)
        db.commit()
