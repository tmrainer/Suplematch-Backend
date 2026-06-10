from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.v1.dependencies import db_session, require_admin, require_moderator_or_admin
from app.db.models import CatalogOverride, CommercialProduct, Pharmacy, User
from app.repositories.admin_repository import AdminRepository
from app.repositories.feedback_repository import FeedbackRepository
from app.repositories.review_repository import ReviewRepository, review_spam_flags
from app.repositories.safety_rule_repository import SafetyRuleRepository
from app.schemas.admin import (
    CatalogQualityOut,
    ImportRunOut,
    IngredientSafetyRuleCreate,
    IngredientSafetyRuleOut,
    IngredientSafetyRuleUpdate,
    ProductAdminOut,
    ProductAdminUpdate,
)
from app.schemas.review import ReviewModerationInput, SupplementReviewModerationOut, SupplementReviewOut
from app.services.product_safety import catalog_verification_status


router = APIRouter()


def _product_out(
    product: CommercialProduct,
    pharmacy: Pharmacy,
    override: CatalogOverride | None = None,
) -> ProductAdminOut:
    verification = catalog_verification_status({
        **(product.raw_payload_json or {}),
        "registro_sanitario": product.registro_sanitario,
        "regulatory_status": product.component_traceable,
    })
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
        preferred=bool(override.preferred) if override else False,
        blocked=bool(override.blocked) if override else product.commercial_status == "blocked",
        override_reason=override.reason if override else None,
        url=product.url,
        last_seen_at=product.last_seen_at,
        verification_status=verification["verification_status"],
        verification_warnings=verification["verification_warnings"],
        restriction_flags_verified=verification["restriction_flags_verified"],
        restriction_flags_inferred=verification["restriction_flags_inferred"],
        label_verified_at=verification["label_verified_at"],
        label_verification_source=verification["label_verification_source"],
    )


def _review_moderation_out(review) -> SupplementReviewModerationOut:
    product = review.product
    component = review.component
    pharmacy = product.pharmacy if product is not None else None
    return SupplementReviewModerationOut(
        id=review.id,
        user_id=review.user_id,
        product_id=review.product_id,
        component_id=review.component_id,
        rating=review.rating,
        effectiveness_score=review.effectiveness_score,
        side_effects_score=review.side_effects_score,
        price_value_score=review.price_value_score,
        comment=review.comment,
        verified_purchase=review.verified_purchase,
        status=review.status,
        created_at=review.created_at,
        product_name=product.commercial_name if product is not None else None,
        pharmacy=pharmacy.name if pharmacy is not None else None,
        component_name=component.canonical_name if component is not None else None,
        spam_flags=review_spam_flags(review.comment),
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
    return [_product_out(product, pharmacy, override) for product, pharmacy, override in rows]


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
    return _product_out(product, pharmacy, repo.latest_override(product.id))


@router.get("/import-runs", response_model=list[ImportRunOut])
def list_import_runs(
    limit: int = 50,
    offset: int = 0,
    _admin: User = Depends(require_admin),
    db: Session = Depends(db_session),
):
    return AdminRepository(db).list_import_runs(limit=limit, offset=offset)


@router.get("/catalog/quality", response_model=CatalogQualityOut)
def catalog_quality(
    _admin: User = Depends(require_admin),
    db: Session = Depends(db_session),
):
    return AdminRepository(db).catalog_quality_summary()


@router.get("/safety-rules", response_model=list[IngredientSafetyRuleOut])
def list_safety_rules(
    active: bool | None = None,
    limit: int = 100,
    offset: int = 0,
    _admin: User = Depends(require_admin),
    db: Session = Depends(db_session),
):
    return SafetyRuleRepository(db).list_rules(active=active, limit=limit, offset=offset)


@router.post("/safety-rules", response_model=IngredientSafetyRuleOut)
def upsert_safety_rule(
    data: IngredientSafetyRuleCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(db_session),
):
    return SafetyRuleRepository(db).upsert_rule(
        **data.model_dump(),
        admin_user_id=admin.id,
    )


@router.patch("/safety-rules/{rule_id}", response_model=IngredientSafetyRuleOut)
def update_safety_rule(
    rule_id: str,
    data: IngredientSafetyRuleUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(db_session),
):
    rule = SafetyRuleRepository(db).update_rule(
        rule_id,
        data.model_dump(exclude_unset=True),
        admin_user_id=admin.id,
    )
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Regla de seguridad no encontrada.")
    return rule


@router.get("/reviews/supplements", response_model=list[SupplementReviewModerationOut])
def list_reviews_for_moderation(
    review_status: str | None = "pending",
    limit: int = 100,
    offset: int = 0,
    _moderator: User = Depends(require_moderator_or_admin),
    db: Session = Depends(db_session),
):
    reviews = ReviewRepository(db).list_supplement_reviews(status=review_status, limit=limit, offset=offset)
    return [_review_moderation_out(review) for review in reviews]


@router.patch("/reviews/supplements/{review_id}", response_model=SupplementReviewOut)
def moderate_review(
    review_id: str,
    data: ReviewModerationInput,
    moderator: User = Depends(require_moderator_or_admin),
    db: Session = Depends(db_session),
):
    review = ReviewRepository(db).moderate_supplement_review(review_id, data.status, moderator_user_id=moderator.id)
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reseña no encontrada.")
    return review


@router.get("/metrics/feedback")
def feedback_metrics(
    _admin: User = Depends(require_admin),
    db: Session = Depends(db_session),
):
    return FeedbackRepository(db).summary(limit=20)
