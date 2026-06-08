from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.dependencies import db_session, optional_current_user
from app.db.models import User
from app.schemas.feedback import FeedbackInput
from app.services.feedback_service import FeedbackService

router = APIRouter()


@router.post("")
def save_feedback(
    data: FeedbackInput,
    db: Session = Depends(db_session),
    user: User | None = Depends(optional_current_user),
):
    return FeedbackService(db).save_feedback(data, user=user)


@router.get("/summary")
def feedback_summary(db: Session = Depends(db_session)):
    return FeedbackService(db).summary()
