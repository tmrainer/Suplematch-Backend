from fastapi import APIRouter

from app.schemas.feedback import FeedbackInput
from app.services.feedback_service import FeedbackService

router = APIRouter()


@router.post("")
def save_feedback(data: FeedbackInput):
    return FeedbackService().save_feedback(data)


@router.get("/summary")
def feedback_summary():
    return FeedbackService().summary()
