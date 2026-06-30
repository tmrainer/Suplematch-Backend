from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.v1.dependencies import current_user, db_session, require_moderator_or_admin
from app.db.models import User
from app.domains.reviews.repositorio_resenas import ReviewRepository
from app.domains.reviews.esquemas import (
    ProductReviewCreate,
    ProductReviewOut,
    ReviewModerationInput,
    SupplementReviewCreate,
    SupplementReviewOut,
)


router = APIRouter()


@router.post("/products", response_model=ProductReviewOut)
def create_product_review(
    data: ProductReviewCreate,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    try:
        return ReviewRepository(db).create_product_review(data, user.id)
    except ValueError as exc:
        if str(exc) == "product_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado.") from exc
        raise


@router.post("/supplements", response_model=SupplementReviewOut)
def create_supplement_review(
    data: SupplementReviewCreate,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    try:
        return ReviewRepository(db).create_supplement_review(data, user.id)
    except ValueError as exc:
        if str(exc) == "product_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado.") from exc
        raise


@router.get("/supplements", response_model=list[SupplementReviewOut])
def list_supplement_reviews(
    product_id: UUID | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(db_session),
):
    return ReviewRepository(db).list_supplement_reviews(
        status="published",
        product_id=product_id,
        limit=limit,
        offset=offset,
    )


@router.get("/products", response_model=list[ProductReviewOut])
def list_product_reviews(
    product_id: UUID | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
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
