from app.main import create_app
from app.ml.runtime import feedback_store
from tests.integration.test_health import asgi_request


def test_feedback_endpoint_persists_event_in_sqlite(tmp_path, monkeypatch):
    monkeypatch.setattr(
        feedback_store,
        "RECOMMENDATION_EVENTS_PATH",
        tmp_path / "recommendation_events.json",
    )
    monkeypatch.setattr(
        feedback_store,
        "USER_FEEDBACK_EVENTS_PATH",
        tmp_path / "user_feedback_events.json",
    )
    monkeypatch.setattr(feedback_store, "FEEDBACK_DB_PATH", tmp_path / "feedback.sqlite3")

    app = create_app()
    payload = {
        "recommendation_id": "rec_test",
        "pack_id": "pack_test",
        "component_ids": ["cmp_vit_d", "cmp_calcium"],
        "rating": 5,
        "conditions": ["DEFICIT_VIT_D"],
        "comment": "Me sirvió para la demo",
    }

    status_code, body = asgi_request(app, "POST", "/api/v1/feedback", payload)

    assert status_code == 200
    assert body["status"] == "saved"
    assert body["recommendation_id"] == "rec_test"
    assert body["rating"] == 5

    events = feedback_store.load_feedback_events()
    assert feedback_store.FEEDBACK_DB_PATH.exists()
    assert len(events) == 1
    assert events[0]["feedback_id"] == body["feedback_id"]
    assert events[0]["pack_id"] == "pack_test"
    assert events[0]["component_ids"] == ["cmp_vit_d", "cmp_calcium"]
    assert events[0]["rating_overall"] == 5
