from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.runtime.migration import MigrationContext
from fastapi import APIRouter, Request, Response
from datetime import datetime, timedelta, timezone
import shutil

from sqlalchemy import case, func, select, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import BASE_DIR, settings
from app.core.observability import metrics
from app.db.database import engine
from app.db.models import (
    AdminAction,
    CatalogImportRun,
    CommercialProduct,
    IngredientSafetyRule,
    LabReport,
    RecommendationFeedback,
    RecommendationSession,
    SupplementReview,
)

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/metrics")
def prometheus_metrics():
    return Response(metrics.prometheus_text(), media_type="text/plain; version=0.0.4; charset=utf-8")


@router.get("/health/ready")
def readiness(request: Request):
    checks = {
        "db": False,
        "alembic_head": False,
        "models": False,
        "catalog_products": 0,
    }

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
        checks["db"] = True

        context = MigrationContext.configure(connection)
        current_revision = context.get_current_revision()
        alembic_config = Config(str(BASE_DIR / "alembic.ini"))
        script = ScriptDirectory.from_config(alembic_config)
        checks["alembic_head"] = current_revision == script.get_current_head()

    models = getattr(request.app.state, "models", {}) or {}
    checks["models"] = bool(models) and all(model is not None for model in models.values())

    from app.db.session import SessionLocal

    with SessionLocal() as db:
        checks["catalog_products"] = int(
            db.scalar(
                select(func.count())
                .select_from(CommercialProduct)
                .where(CommercialProduct.commercial_status.in_(["active", "preferred"]))
            )
            or 0
        )

    ready = checks["db"] and checks["alembic_head"] and checks["models"] and checks["catalog_products"] > 0
    return {
        "status": "ready" if ready else "degraded",
        "checks": checks,
    }


@router.get("/health/ops")
def operational_health(request: Request):
    from app.db.session import SessionLocal

    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)

    models = getattr(request.app.state, "models", {}) or {}

    with SessionLocal() as db:
        product_counts = db.execute(
            select(
                func.count(CommercialProduct.id),
                func.sum(case((CommercialProduct.commercial_status == "active", 1), else_=0)),
                func.sum(case((CommercialProduct.availability == "available", 1), else_=0)),
                func.sum(case((CommercialProduct.registro_sanitario.is_not(None), 1), else_=0)),
            )
        ).one()

        recommendation_counts = db.execute(
            select(
                func.count(RecommendationSession.id),
                func.sum(case((RecommendationSession.created_at >= last_24h, 1), else_=0)),
                func.sum(case((RecommendationSession.created_at >= last_7d, 1), else_=0)),
                func.sum(case((func.jsonb_array_length(RecommendationSession.profile_warnings_json) > 0, 1), else_=0)),
            )
        ).one()

        try:
            lab_counts = db.execute(
                select(
                    func.count(LabReport.id),
                    func.sum(case((LabReport.created_at >= last_7d, 1), else_=0)),
                    func.sum(case((LabReport.analysis_json["commercial_recommendations_blocked"].astext == "true", 1), else_=0)),
                )
            ).one()
        except SQLAlchemyError:
            db.rollback()
            lab_counts = (0, 0, 0)

        pending_reviews = db.scalar(
            select(func.count()).select_from(SupplementReview).where(SupplementReview.status == "pending")
        ) or 0
        hidden_reviews = db.scalar(
            select(func.count()).select_from(SupplementReview).where(SupplementReview.status == "hidden")
        ) or 0
        try:
            safety_rules_active = db.scalar(
                select(func.count()).select_from(IngredientSafetyRule).where(IngredientSafetyRule.active.is_(True))
            ) or 0
        except SQLAlchemyError:
            db.rollback()
            safety_rules_active = 0
        product_payloads = list(db.scalars(select(CommercialProduct.raw_payload_json)))
        catalog_with_verified_flags = sum(1 for payload in product_payloads if (payload or {}).get("restriction_flags_verified"))
        catalog_with_label_source = sum(1 for payload in product_payloads if (payload or {}).get("label_verification_source"))
        feedback_7d = db.scalar(
            select(func.count()).select_from(RecommendationFeedback).where(RecommendationFeedback.created_at >= last_7d)
        ) or 0
        last_import = db.scalar(
            select(CatalogImportRun).order_by(CatalogImportRun.started_at.desc()).limit(1)
        )
        admin_actions_7d = db.scalar(
            select(func.count()).select_from(AdminAction).where(AdminAction.created_at >= last_7d)
        ) or 0

    catalog_total, catalog_active, catalog_available, catalog_with_rs = [int(value or 0) for value in product_counts]
    rec_total, rec_24h, rec_7d, rec_with_warnings = [int(value or 0) for value in recommendation_counts]
    lab_total, lab_7d, lab_blocked = [int(value or 0) for value in lab_counts]
    tesseract_available = shutil.which("tesseract") is not None

    checks = {
        "models_loaded": bool(models) and all(model is not None for model in models.values()),
        "catalog_has_products": catalog_active > 0,
        "pending_review_backlog_ok": int(pending_reviews) < 100,
        "ingredient_safety_rules_loaded": int(safety_rules_active) > 0,
    }

    return {
        "status": "ok" if all(checks.values()) else "attention",
        "generated_at": now.isoformat(),
        "environment": settings.ENVIRONMENT,
        "checks": checks,
        "catalog": {
            "products_total": catalog_total,
            "products_active": catalog_active,
            "products_available": catalog_available,
            "products_with_registro_sanitario": catalog_with_rs,
            "products_with_verified_restriction_flags": int(catalog_with_verified_flags),
            "products_with_label_source": int(catalog_with_label_source),
        },
        "recommendations": {
            "total": rec_total,
            "last_24h": rec_24h,
            "last_7d": rec_7d,
            "with_profile_warnings": rec_with_warnings,
        },
        "feedback": {
            "last_7d": int(feedback_7d),
        },
        "reviews": {
            "pending": int(pending_reviews),
            "hidden_spam_or_flagged": int(hidden_reviews),
        },
        "safety": {
            "active_ingredient_rules": int(safety_rules_active),
        },
        "labs": {
            "reports_total": lab_total,
            "reports_last_7d": lab_7d,
            "reports_blocking_commercial_recommendations": lab_blocked,
            "ocr_engine_available": tesseract_available,
            "ocr_engine": "tesseract" if tesseract_available else None,
        },
        "admin": {
            "actions_last_7d": int(admin_actions_7d),
        },
        "catalog_import": None if last_import is None else {
            "status": last_import.status,
            "started_at": last_import.started_at.isoformat() if last_import.started_at else None,
            "finished_at": last_import.finished_at.isoformat() if last_import.finished_at else None,
            "total_accepted": last_import.total_accepted,
            "total_rejected": last_import.total_rejected,
        },
    }
