from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.dependencies import db_session, require_admin, require_moderator_or_admin
from app.db.models import AdminAction, CatalogOverride, CommercialProduct, Pharmacy, ProductPriceSnapshot, User
from app.domains.admin.repositorio_admin import AdminRepository
from app.domains.feedback.repositorio_feedback import FeedbackRepository
from app.domains.reviews.repositorio_resenas import ReviewRepository, review_spam_flags
from app.domains.catalog.repositorio_reglas_seguridad import SafetyRuleRepository
from app.domains.admin.esquemas import (
    CatalogCandidateActionInput,
    CatalogCandidateActionOut,
    CatalogCandidateListOut,
    CatalogCandidatePromoteInput,
    CatalogCandidatePromoteOut,
    CatalogJobRunInput,
    CatalogJobRunOut,
    CatalogJobApproveOut,
    CatalogJobCancelOut,
    CatalogJobStatusOut,
    CatalogQualityOut,
    ImportRunOut,
    IngredientSafetyRuleCreate,
    IngredientSafetyRuleOut,
    IngredientSafetyRuleUpdate,
    ProductAdminOut,
    ProductAdminUpdate,
    ProductPriceSnapshotOut,
)
from app.domains.admin.servicio_candidatos_catalogo import CatalogCandidateService
from app.domains.admin.servicio_jobs_catalogo import (
    approve_catalog_import,
    cancel_catalog_job,
    catalog_job_status,
    start_catalog_job,
)
from app.domains.reviews.esquemas import ReviewModerationInput, SupplementReviewModerationOut, SupplementReviewOut
from app.domains.catalog.seguridad_productos import catalog_verification_status
from app.domains.catalog.servicio_catalogo_productos import ProductCatalogService


router = APIRouter()


def _product_out(
    product: CommercialProduct,
    pharmacy: Pharmacy,
    override: CatalogOverride | None = None,
) -> ProductAdminOut:
    payload = {
        **(product.raw_payload_json or {}),
        "registro_sanitario": product.registro_sanitario,
        "regulatory_status": product.component_traceable,
    }
    verification = catalog_verification_status(payload)
    component_count = max(1, len(product.components or []))
    quality_flags = ProductCatalogService()._commercial_quality_flags({
        **payload,
        "commercial_name": product.commercial_name,
        "formal_name": product.formal_name,
        "brand": product.brand,
        "ingredient": " ".join(link.ingredient or "" for link in product.components or []),
        "price": product.price,
        "availability": product.availability,
        "product_component_count": component_count,
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
        commercial_quality_flags=quality_flags,
        product_component_count=component_count,
        component_traceable=product.component_traceable,
        label_verified_at=verification["label_verified_at"],
        label_verification_source=verification["label_verification_source"],
        commercial_confidence_score=payload.get("commercial_confidence_score"),
        commercial_confidence_level=payload.get("commercial_confidence_level"),
        commercial_confidence_reasons=payload.get("commercial_confidence_reasons"),
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
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
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


@router.get("/products/{product_id}/price-snapshots", response_model=list[ProductPriceSnapshotOut])
def product_price_snapshots(
    product_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    _admin: User = Depends(require_admin),
    db: Session = Depends(db_session),
):
    return list(
        db.scalars(
            select(ProductPriceSnapshot)
            .where(ProductPriceSnapshot.product_id == product_id)
            .order_by(ProductPriceSnapshot.seen_at.desc())
            .limit(limit)
        )
    )


@router.get("/import-runs", response_model=list[ImportRunOut])
def list_import_runs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
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


@router.get("/catalog/candidates", response_model=CatalogCandidateListOut)
def list_catalog_candidates(
    component: str | None = None,
    status_filter: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(require_admin),
):
    return CatalogCandidateService().list_candidates(
        component=component,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )


@router.patch("/catalog/candidates/{candidate_id}", response_model=CatalogCandidateActionOut)
def update_catalog_candidate(
    candidate_id: str,
    data: CatalogCandidateActionInput,
    admin: User = Depends(require_admin),
    db: Session = Depends(db_session),
):
    service = CatalogCandidateService(db)
    try:
        candidate = service.update_candidate_status(
            candidate_id,
            next_status=data.status,
            reason=data.reason,
            admin_user_id=admin.id,
        )
        db.commit()
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return CatalogCandidateActionOut(candidate=candidate, message="Candidato actualizado.")


@router.post("/catalog/candidates/{candidate_id}/promote", response_model=CatalogCandidatePromoteOut)
def promote_catalog_candidate(
    candidate_id: str,
    data: CatalogCandidatePromoteInput,
    admin: User = Depends(require_admin),
    db: Session = Depends(db_session),
):
    service = CatalogCandidateService(db)
    try:
        candidate, product_id = service.promote_candidate(
            candidate_id,
            reason=data.reason,
            admin_user_id=admin.id,
        )
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return CatalogCandidatePromoteOut(
        candidate=candidate,
        product_id=product_id,
        message="Candidato promovido al catálogo activo.",
    )


@router.get("/catalog/jobs/status", response_model=CatalogJobStatusOut)
def catalog_job_status_endpoint(
    _admin: User = Depends(require_admin),
):
    return catalog_job_status()


@router.post("/catalog/jobs/run", response_model=CatalogJobRunOut)
def run_catalog_job(
    data: CatalogJobRunInput,
    admin: User = Depends(require_admin),
    db: Session = Depends(db_session),
):
    pharmacies = [item.strip() for item in data.pharmacies if item.strip()]
    result = start_catalog_job(
        mode=data.mode,
        limit_per_pharmacy=data.limit_per_pharmacy,
        pharmacies=pharmacies,
        max_raw_age_hours=data.max_raw_age_hours,
        import_to_postgres=data.import_to_postgres,
        requested_by=str(admin.id),
    )
    db.add(
        AdminAction(
            admin_user_id=admin.id,
            action_type="catalog_job_requested",
            entity_type="catalog_job",
            entity_id=data.mode,
            before_json={},
            after_json={
                **data.model_dump(),
                "pharmacies": pharmacies,
                "accepted": result["accepted"],
            },
        )
    )
    db.commit()
    return result


@router.post("/catalog/jobs/cancel", response_model=CatalogJobCancelOut)
def cancel_latest_catalog_job(
    admin: User = Depends(require_admin),
    db: Session = Depends(db_session),
):
    result = cancel_catalog_job(job_id=None, cancelled_by=str(admin.id))
    db.add(
        AdminAction(
            admin_user_id=admin.id,
            action_type="catalog_job_cancel_requested",
            entity_type="catalog_job",
            entity_id=None,
            before_json={},
            after_json={"cancelled": result["cancelled"]},
        )
    )
    db.commit()
    return result


@router.post("/catalog/jobs/{job_id}/cancel", response_model=CatalogJobCancelOut)
def cancel_catalog_job_by_id(
    job_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(db_session),
):
    result = cancel_catalog_job(job_id=job_id, cancelled_by=str(admin.id))
    db.add(
        AdminAction(
            admin_user_id=admin.id,
            action_type="catalog_job_cancel_requested",
            entity_type="catalog_job",
            entity_id=job_id,
            before_json={},
            after_json={"cancelled": result["cancelled"]},
        )
    )
    db.commit()
    return result


@router.post("/catalog/jobs/{job_id}/approve-import", response_model=CatalogJobApproveOut)
def approve_catalog_job_import(
    job_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(db_session),
):
    result = approve_catalog_import(job_id=job_id, approved_by=str(admin.id))
    db.add(
        AdminAction(
            admin_user_id=admin.id,
            action_type="catalog_job_approve_import",
            entity_type="catalog_job",
            entity_id=job_id,
            before_json={},
            after_json={"approved": result["approved"]},
        )
    )
    db.commit()
    return result


@router.get("/safety-rules", response_model=list[IngredientSafetyRuleOut])
def list_safety_rules(
    active: bool | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
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
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _moderator: User = Depends(require_moderator_or_admin),
    db: Session = Depends(db_session),
):
    reviews = ReviewRepository(db).list_supplement_reviews(status=review_status, limit=limit, offset=offset)
    return [_review_moderation_out(review) for review in reviews]


@router.get("/reviews/products", response_model=list[SupplementReviewModerationOut])
def list_product_reviews_for_moderation(
    review_status: str | None = "pending",
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
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


@router.patch("/reviews/products/{review_id}", response_model=SupplementReviewOut)
def moderate_product_review(
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
