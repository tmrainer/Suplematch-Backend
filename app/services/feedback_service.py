from app.schemas.feedback import FeedbackInput
from app.ml.runtime.feedback_store import get_feedback_summary, save_feedback_event


class FeedbackService:
    def save_feedback(self, data: FeedbackInput) -> dict:
        feedback_id = save_feedback_event(
            recommendation_id=data.recommendation_id,
            pack_id=data.pack_id,
            component_ids=data.component_ids,
            rating_overall=data.rating,
            conditions_context=data.conditions,
            comment=data.comment,
        )

        return {
            "status": "saved",
            "feedback_id": feedback_id,
            "recommendation_id": data.recommendation_id,
            "rating": data.rating,
        }

    def summary(self) -> dict:
        return get_feedback_summary()
