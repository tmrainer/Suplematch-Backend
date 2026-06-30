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
