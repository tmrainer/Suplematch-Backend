from pathlib import Path
from tempfile import TemporaryDirectory

from app.ml.runtime import feedback_store
from app.ml.runtime.feedback_reranker import rerank_packs


def _recommendations():
    return [
        {
            "component_id": "cmp_vit_d",
            "nombre": "Vitamin D",
            "condicion": "DEFICIT_VIT_D",
            "score": 0.72,
        },
        {
            "component_id": "cmp_calcium",
            "nombre": "Calcium",
            "condicion": "DEFICIT_CALCIO",
            "score": 0.70,
        },
        {
            "component_id": "cmp_magnesium",
            "nombre": "Magnesium",
            "condicion": "soporte_funcional",
            "score": 0.68,
        },
    ]


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
            callback()
        finally:
            feedback_store.RECOMMENDATION_EVENTS_PATH = original_recommendation_path
            feedback_store.USER_FEEDBACK_EVENTS_PATH = original_feedback_path
            feedback_store.FEEDBACK_DB_PATH = original_db_path


def test_feedback_changes_pack_scores_visibly():
    def run():
        conditions = ["DEFICIT_VIT_D", "DEFICIT_CALCIO"]
        base_pack = rerank_packs(_recommendations(), conditions)[0]

        assert base_pack["feedback_count"] == 0
        assert base_pack["score_feedback"] == 0.70

        feedback_store.save_feedback_event(
            recommendation_id="rec_1",
            pack_id=base_pack["pack_id"],
            component_ids=base_pack["component_ids"],
            rating_overall=5,
        )
        one_positive = rerank_packs(_recommendations(), conditions)[0]

        assert one_positive["feedback_count"] == 1
        assert one_positive["score_feedback"] > base_pack["score_feedback"]
        assert one_positive["score_final"] > base_pack["score_final"]

        for index in range(2, 6):
            feedback_store.save_feedback_event(
                recommendation_id=f"rec_{index}",
                pack_id=base_pack["pack_id"],
                component_ids=base_pack["component_ids"],
                rating_overall=5,
            )

        many_positive = rerank_packs(_recommendations(), conditions)[0]

        assert many_positive["feedback_count"] == 5
        assert many_positive["score_feedback"] > one_positive["score_feedback"]
        assert many_positive["score_final"] > one_positive["score_final"]

    _with_temp_feedback_store(run)


def test_negative_feedback_lowers_pack_scores():
    def run():
        conditions = ["DEFICIT_VIT_D", "DEFICIT_CALCIO"]
        base_pack = rerank_packs(_recommendations(), conditions)[0]

        for index in range(1, 4):
            feedback_store.save_feedback_event(
                recommendation_id=f"rec_negative_{index}",
                pack_id=base_pack["pack_id"],
                component_ids=base_pack["component_ids"],
                rating_overall=1,
            )

        negative = rerank_packs(_recommendations(), conditions)[0]

        assert negative["feedback_count"] == 3
        assert negative["score_feedback"] < base_pack["score_feedback"]
        assert negative["score_final"] < base_pack["score_final"]

    _with_temp_feedback_store(run)
