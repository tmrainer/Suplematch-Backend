from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import AdminAction, CommercialProduct, CommercialProductComponent, SupplementReview
from app.domains.reviews.esquemas import ProductReviewCreate, SupplementReviewCreate


def review_spam_flags(comment: str | None) -> list[str]:
    text = (comment or "").strip().lower()
    if not text:
        return []

    flags = []
    if "http://" in text or "https://" in text or "www." in text:
        flags.append("contains_url")
    if "@" in text and "." in text:
        flags.append("contains_contact")
    if any(char * 8 in text for char in set(text)):
        flags.append("repeated_characters")
    if any(keyword in text for keyword in ("cura", "curó", "curo", "garantizado", "milagro", "sanó", "sano mi")):
        flags.append("medical_claim")
    if any(keyword in text for keyword in ("dni", "telefono", "teléfono", "whatsapp", "direccion", "dirección")):
        flags.append("personal_data")
    if any(keyword in text for keyword in ("mg/kg", "sobredosis", "megadosis", "duplicar dosis", "triplicar dosis")):
        flags.append("unsafe_dosing")

    words = [word.strip(".,;:!?¡¿()[]{}") for word in text.split()]
    words = [word for word in words if word]
    if len(words) >= 8:
        unique_ratio = len(set(words)) / len(words)
        if unique_ratio <= 0.45:
            flags.append("repeated_words")

    return flags


class ReviewRepository:
    def __init__(self, db: Session):
        self.db = db

    def _primary_component_id_for_product(self, product_id: UUID) -> UUID | None:
        return self.db.scalar(
            select(CommercialProductComponent.component_id)
            .where(CommercialProductComponent.product_id == product_id)
            .order_by(CommercialProductComponent.match_score.desc().nullslast())
            .limit(1)
        )

    def create_product_review(self, data: ProductReviewCreate, user_id: UUID | None) -> SupplementReview:
        product = self.db.get(CommercialProduct, data.product_id)
        if product is None:
            raise ValueError("product_not_found")

        spam_flags = review_spam_flags(data.comment)
        is_quick_recommendation = data.source == "quick_recommendation" and not spam_flags and not (data.comment or "").strip()
        review = SupplementReview(
            user_id=user_id,
            product_id=data.product_id,
            component_id=self._primary_component_id_for_product(data.product_id),
            rating=data.rating,
            effectiveness_score=data.effectiveness_score,
            side_effects_score=data.side_effects_score,
            price_value_score=data.price_value_score,
            comment=data.comment,
            verified_purchase=False,
            status="hidden" if spam_flags else "published" if is_quick_recommendation else "pending",
        )
        self.db.add(review)
        self.db.commit()
        self.db.refresh(review)
        return review

    def create_supplement_review(self, data: SupplementReviewCreate, user_id: UUID | None) -> SupplementReview:
        return self.create_product_review(data, user_id)

    def list_supplement_reviews(
        self,
        *,
        status: str | None = "published",
        product_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SupplementReview]:
        query = (
            select(SupplementReview)
            .options(
                selectinload(SupplementReview.product).selectinload(CommercialProduct.pharmacy),
                selectinload(SupplementReview.component),
            )
            .order_by(SupplementReview.created_at.desc())
        )
        if status:
            query = query.where(SupplementReview.status == status)
        if product_id:
            query = query.where(SupplementReview.product_id == product_id)
        return list(self.db.scalars(query.offset(offset).limit(limit)))

    def moderate_supplement_review(
        self,
        review_id: UUID | str,
        status: str,
        *,
        moderator_user_id: UUID | None = None,
    ) -> SupplementReview | None:
        review = self.db.get(SupplementReview, review_id)
        if review is None:
            return None
        before = {"status": review.status}
        review.status = status
        self.db.add(
            AdminAction(
                admin_user_id=moderator_user_id,
                action_type="moderate_supplement_review",
                entity_type="supplement_review",
                entity_id=str(review.id),
                before_json=before,
                after_json={
                    "status": status,
                    "spam_flags": review_spam_flags(review.comment),
                    "product_id": str(review.product_id) if review.product_id else None,
                },
            )
        )
        self.db.commit()
        self.db.refresh(review)
        return review
