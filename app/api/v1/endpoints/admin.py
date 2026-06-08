from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.v1.dependencies import db_session, require_admin, require_moderator_or_admin
from app.db.models import CommercialProduct, Pharmacy, User
from app.repositories.admin_repository import AdminRepository
from app.repositories.feedback_repository import FeedbackRepository
from app.repositories.review_repository import ReviewRepository
from app.schemas.admin import ImportRunOut, ProductAdminOut, ProductAdminUpdate
from app.schemas.review import ReviewModerationInput, SupplementReviewOut


router = APIRouter()


def _product_out(product: CommercialProduct, pharmacy: Pharmacy) -> ProductAdminOut:
    return ProductAdminOut(
        id=product.id,
        pharmacy=pharmacy.name,
        commercial_name=product.commercial_name,
        brand=product.brand,
        registro_sanitario=product.registro_sanitario,
        price=product.price,
        currency=product.currency,
        availability=product.availability,
        commercial_status=product.commercial_status,
        url=product.url,
        last_seen_at=product.last_seen_at,
    )


@router.get("/products", response_model=list[ProductAdminOut])
def list_products(
    limit: int = 100,
    offset: int = 0,
    status_filter: str | None = None,
    _admin: User = Depends(require_admin),
    db: Session = Depends(db_session),
):
    rows = AdminRepository(db).list_products(limit=limit, offset=offset, status=status_filter)
    return [_product_out(product, pharmacy) for product, pharmacy in rows]


@router.patch("/products/{product_id}", response_model=ProductAdminOut)
def update_product(
    product_id: str,
    data: ProductAdminUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(db_session),
):
    repo = AdminRepository(db)
    product = repo.update_product(product_id, data, admin_user_id=admin.id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado.")
    pharmacy = product.pharmacy
    return _product_out(product, pharmacy)


@router.get("/import-runs", response_model=list[ImportRunOut])
def list_import_runs(
    limit: int = 50,
    offset: int = 0,
    _admin: User = Depends(require_admin),
    db: Session = Depends(db_session),
):
    return AdminRepository(db).list_import_runs(limit=limit, offset=offset)


@router.get("/reviews/supplements", response_model=list[SupplementReviewOut])
def list_reviews_for_moderation(
    review_status: str | None = "pending",
    limit: int = 100,
    offset: int = 0,
    _moderator: User = Depends(require_moderator_or_admin),
    db: Session = Depends(db_session),
):
    return ReviewRepository(db).list_supplement_reviews(status=review_status, limit=limit, offset=offset)


@router.patch("/reviews/supplements/{review_id}", response_model=SupplementReviewOut)
def moderate_review(
    review_id: str,
    data: ReviewModerationInput,
    _moderator: User = Depends(require_moderator_or_admin),
    db: Session = Depends(db_session),
):
    review = ReviewRepository(db).moderate_supplement_review(review_id, data.status)
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reseña no encontrada.")
    return review


@router.get("/metrics/feedback")
def feedback_metrics(
    _admin: User = Depends(require_admin),
    db: Session = Depends(db_session),
):
    return FeedbackRepository(db).summary(limit=20)
