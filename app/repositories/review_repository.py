from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SupplementReview
from app.schemas.review import SupplementReviewCreate


class ReviewRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_supplement_review(self, data: SupplementReviewCreate, user_id: UUID | None) -> SupplementReview:
        review = SupplementReview(
            user_id=user_id,
            product_id=data.product_id,
            component_id=data.component_id,
            rating=data.rating,
            effectiveness_score=data.effectiveness_score,
            side_effects_score=data.side_effects_score,
            price_value_score=data.price_value_score,
            comment=data.comment,
            verified_purchase=False,
            status="pending",
        )
        self.db.add(review)
        self.db.commit()
        self.db.refresh(review)
        return review

    def list_supplement_reviews(
        self,
        *,
        status: str | None = "published",
        product_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SupplementReview]:
        query = select(SupplementReview).order_by(SupplementReview.created_at.desc())
        if status:
            query = query.where(SupplementReview.status == status)
        if product_id:
            query = query.where(SupplementReview.product_id == product_id)
        return list(self.db.scalars(query.offset(offset).limit(limit)))

    def moderate_supplement_review(self, review_id: UUID | str, status: str) -> SupplementReview | None:
        review = self.db.get(SupplementReview, review_id)
        if review is None:
            return None
        review.status = status
        self.db.commit()
        self.db.refresh(review)
        return review
