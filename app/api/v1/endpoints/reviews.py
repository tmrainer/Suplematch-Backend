from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.v1.dependencies import current_user, db_session, require_moderator_or_admin
from app.db.models import User
from app.repositories.review_repository import ReviewRepository
from app.schemas.review import (
    ReviewModerationInput,
    SupplementReviewCreate,
    SupplementReviewOut,
)


router = APIRouter()


@router.post("/supplements", response_model=SupplementReviewOut)
def create_supplement_review(
    data: SupplementReviewCreate,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    return ReviewRepository(db).create_supplement_review(data, user.id)


@router.get("/supplements", response_model=list[SupplementReviewOut])
def list_supplement_reviews(
    product_id: UUID | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(db_session),
):
    return ReviewRepository(db).list_supplement_reviews(
        status="published",
        product_id=product_id,
        limit=limit,
        offset=offset,
    )


@router.patch("/supplements/{review_id}/moderation", response_model=SupplementReviewOut)
def moderate_supplement_review(
    review_id: str,
    data: ReviewModerationInput,
    _moderator: User = Depends(require_moderator_or_admin),
    db: Session = Depends(db_session),
):
    review = ReviewRepository(db).moderate_supplement_review(review_id, data.status)
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reseña no encontrada.")
    return review
