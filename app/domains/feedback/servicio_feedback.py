from app.domains.feedback.esquemas import FeedbackInput
from app.db.models import User
from app.ml.runtime.feedback_store import get_feedback_summary, save_feedback_event
from app.domains.feedback.repositorio_feedback import FeedbackRepository


class FeedbackService:
    def __init__(self, db=None):
        self.db = db


    def save_feedback(self, data: FeedbackInput, user: User | None = None) -> dict:
        save_feedback_event(
            recommendation_id=data.recommendation_id,
            pack_id=data.pack_id,
            component_ids=data.component_ids,
            rating_overall=data.rating,
            conditions_context=data.conditions,
            comment=data.comment,
        )

        if self.db is not None:
            feedback = FeedbackRepository(self.db).save_feedback(data, user_id=user.id if user else None)
            return {
                "status": "saved",
                "feedback_id": str(feedback.id),
                "recommendation_id": data.recommendation_id,
                "rating": data.rating,
            }

        feedback_id = f"fb_{data.recommendation_id}"
        return {
            "status": "saved",
            "feedback_id": feedback_id,
            "recommendation_id": data.recommendation_id,
            "rating": data.rating,
        }

    def summary(self) -> dict:
        if self.db is not None:
            return FeedbackRepository(self.db).summary()

        return get_feedback_summary()
