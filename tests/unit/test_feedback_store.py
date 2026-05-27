import json
from pathlib import Path
from tempfile import TemporaryDirectory

from app.ml.runtime import feedback_store


def _with_temp_feedback_store(callback):
    original_recommendation_path = feedback_store.RECOMMENDATION_EVENTS_PATH
    original_feedback_path = feedback_store.USER_FEEDBACK_EVENTS_PATH
    original_db_path = feedback_store.FEEDBACK_DB_PATH

    with TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        feedback_store.RECOMMENDATION_EVENTS_PATH = tmp_path / "recommendation_events.json"
        feedback_store.USER_FEEDBACK_EVENTS_PATH = tmp_path / "user_feedback_events.json"
        feedback_store.FEEDBACK_DB_PATH = tmp_path / "feedback.sqlite3"

        try:
            callback(tmp_path)
        finally:
            feedback_store.RECOMMENDATION_EVENTS_PATH = original_recommendation_path
            feedback_store.USER_FEEDBACK_EVENTS_PATH = original_feedback_path
            feedback_store.FEEDBACK_DB_PATH = original_db_path


def test_feedback_store_persists_events_in_sqlite():
    def run(_tmp_path):
        recommendation_id = feedback_store.save_recommendation_event(
            conditions=["DEFICIT_VIT_D"],
            packs_ranked=[{"pack_id": "pack_demo", "rank": 1}],
        )
        feedback_id = feedback_store.save_feedback_event(
            recommendation_id=recommendation_id,
            pack_id="pack_demo",
            component_ids=["cmp_vit_d"],
            rating_overall=5,
        )

        assert feedback_store.FEEDBACK_DB_PATH.exists()
        assert feedback_store.load_recommendation_events()[0]["recommendation_id"] == recommendation_id
        assert feedback_store.load_feedback_events()[0]["feedback_id"] == feedback_id

        summary = feedback_store.get_feedback_summary()
        assert summary["total_feedback_events"] == 1
        assert summary["packs_with_feedback"] == 1
        assert summary["top_rated_packs"][0]["pack_id"] == "pack_demo"

    _with_temp_feedback_store(run)


def test_feedback_store_migrates_existing_json_events_to_sqlite():
    def run(_tmp_path):
        feedback_store.RECOMMENDATION_EVENTS_PATH.write_text(
            json.dumps(
                [
                    {
                        "recommendation_id": "rec_json",
                        "timestamp": "2026-01-01T00:00:00+00:00",
                        "conditions": ["DEFICIT_VIT_D"],
                        "packs_ranked": [{"pack_id": "pack_json", "rank": 1}],
                    }
                ]
            ),
            encoding="utf-8",
        )
        feedback_store.USER_FEEDBACK_EVENTS_PATH.write_text(
            json.dumps(
                [
                    {
                        "feedback_id": "fb_json",
                        "timestamp": "2026-01-01T00:01:00+00:00",
                        "recommendation_id": "rec_json",
                        "pack_id": "pack_json",
                        "component_ids": ["cmp_vit_d"],
                        "rating_overall": 5,
                        "conditions_context": ["DEFICIT_VIT_D"],
                        "comment": None,
                        "extra": {},
                    }
                ]
            ),
            encoding="utf-8",
        )

        assert feedback_store.load_recommendation_events()[0]["recommendation_id"] == "rec_json"
        assert feedback_store.load_feedback_events()[0]["feedback_id"] == "fb_json"
        assert feedback_store.get_feedback_summary()["packs_with_feedback"] == 1

    _with_temp_feedback_store(run)
