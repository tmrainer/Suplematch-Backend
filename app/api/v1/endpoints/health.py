from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.runtime.migration import MigrationContext
from fastapi import APIRouter, Request, Response
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
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


def _read_json_report(path: Path) -> dict | None:
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _latest_json_report(pattern: str) -> dict | None:
    try:
        matches = sorted(BASE_DIR.glob(pattern), key=lambda item: item.stat().st_mtime, reverse=True)
    except OSError:
        return None
    for path in matches:
        report = _read_json_report(path)
        if report is not None:
            report["_path"] = str(path)
            return report
    return None


def _latest_existing_report(pattern: str) -> dict | None:
    try:
        matches = sorted(BASE_DIR.glob(pattern), key=lambda item: item.stat().st_mtime, reverse=True)
    except OSError:
        return None
    if not matches:
        return None
    path = matches[0]
    try:
        stat = path.stat()
    except OSError:
        return None
    return {
        "_path": str(path),
        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "size_bytes": stat.st_size,
    }


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/metrics")
def prometheus_metrics():
    return Response(
        metrics.prometheus_text() + _database_metrics_text(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


def _database_metrics_text() -> str:
    from app.db.session import SessionLocal

    try:
        with SessionLocal() as db:
            products_active = int(
                db.scalar(
                    select(func.count())
                    .select_from(CommercialProduct)
                    .where(CommercialProduct.commercial_status.in_(["active", "preferred"]))
                )
                or 0
            )
            products_available = int(
                db.scalar(
                    select(func.count())
                    .select_from(CommercialProduct)
                    .where(CommercialProduct.availability == "available")
                )
                or 0
            )
            recommendations_total = int(
                db.scalar(select(func.count()).select_from(RecommendationSession)) or 0
            )
            feedback_total = int(
                db.scalar(select(func.count()).select_from(RecommendationFeedback)) or 0
            )
            reviews_pending = int(
                db.scalar(
                    select(func.count())
                    .select_from(SupplementReview)
                    .where(SupplementReview.status == "pending")
                )
                or 0
            )
            lab_reports_total = int(
                db.scalar(select(func.count()).select_from(LabReport)) or 0
            )
            lab_reports_blocking = int(
                db.scalar(
                    select(func.count())
                    .select_from(LabReport)
                    .where(LabReport.analysis_json["commercial_recommendations_blocked"].astext == "true")
                )
                or 0
            )
            safety_rules_active = int(
                db.scalar(
                    select(func.count())
                    .select_from(IngredientSafetyRule)
                    .where(IngredientSafetyRule.active.is_(True))
                )
                or 0
            )
            product_payloads = list(db.scalars(select(CommercialProduct.raw_payload_json)))
            products_with_verified_flags = sum(
                1 for payload in product_payloads if (payload or {}).get("restriction_flags_verified")
            )
            products_with_label_source = sum(
                1 for payload in product_payloads if (payload or {}).get("label_verification_source")
            )
    except SQLAlchemyError:
        return "\n# suplematch_database_metrics_unavailable 1\n"

    model2_report = _read_json_report(BASE_DIR / "data/reports/supplement_model/01_model2_summary.json")
    commercial_engine_report = _read_json_report(BASE_DIR / "data/reports/commercial_engine/01_commercial_engine_summary.json")
    ocr_report = _read_json_report(BASE_DIR / "data/reports/labs/01_ocr_lab_summary.json")
    scraping_report = _read_json_report(BASE_DIR / "data/reports/scraping/catalog_pipeline_current_report.json")
    operational_report = _read_json_report(BASE_DIR / "data/reports/operational/quality_summary.json")

    def passed(report: dict | None) -> int:
        return 1 if report and report.get("status") == "passed" else 0

    return "\n".join([
        "# HELP suplematch_catalog_products_active Active or preferred commercial products.",
        "# TYPE suplematch_catalog_products_active gauge",
        f"suplematch_catalog_products_active {products_active}",
        "# HELP suplematch_catalog_products_available Products currently marked as available.",
        "# TYPE suplematch_catalog_products_available gauge",
        f"suplematch_catalog_products_available {products_available}",
        "# HELP suplematch_recommendation_sessions_total Recommendation sessions stored in PostgreSQL.",
        "# TYPE suplematch_recommendation_sessions_total gauge",
        f"suplematch_recommendation_sessions_total {recommendations_total}",
        "# HELP suplematch_feedback_events_total Recommendation feedback events stored in PostgreSQL.",
        "# TYPE suplematch_feedback_events_total gauge",
        f"suplematch_feedback_events_total {feedback_total}",
        "# HELP suplematch_reviews_pending Pending supplement reviews.",
        "# TYPE suplematch_reviews_pending gauge",
        f"suplematch_reviews_pending {reviews_pending}",
        "# HELP suplematch_lab_reports_total Lab reports stored in PostgreSQL.",
        "# TYPE suplematch_lab_reports_total gauge",
        f"suplematch_lab_reports_total {lab_reports_total}",
        "# HELP suplematch_lab_reports_blocking_commercial_recommendations Lab reports that block commercial recommendations.",
        "# TYPE suplematch_lab_reports_blocking_commercial_recommendations gauge",
        f"suplematch_lab_reports_blocking_commercial_recommendations {lab_reports_blocking}",
        "# HELP suplematch_ingredient_safety_rules_active Active ingredient safety rules.",
        "# TYPE suplematch_ingredient_safety_rules_active gauge",
        f"suplematch_ingredient_safety_rules_active {safety_rules_active}",
        "# HELP suplematch_catalog_products_with_verified_restriction_flags Products with verified restriction flags.",
        "# TYPE suplematch_catalog_products_with_verified_restriction_flags gauge",
        f"suplematch_catalog_products_with_verified_restriction_flags {products_with_verified_flags}",
        "# HELP suplematch_catalog_products_with_label_source Products with recorded label verification source.",
        "# TYPE suplematch_catalog_products_with_label_source gauge",
        f"suplematch_catalog_products_with_label_source {products_with_label_source}",
        "# HELP suplematch_ocr_engine_available Whether tesseract OCR is available in the runtime.",
        "# TYPE suplematch_ocr_engine_available gauge",
        f"suplematch_ocr_engine_available {1 if shutil.which('tesseract') is not None else 0}",
        "# HELP suplematch_model2_quality_ok Latest Model 2 quality report status.",
        "# TYPE suplematch_model2_quality_ok gauge",
        f"suplematch_model2_quality_ok {passed(model2_report)}",
        "# HELP suplematch_commercial_engine_quality_ok Latest commercial engine report status.",
        "# TYPE suplematch_commercial_engine_quality_ok gauge",
        f"suplematch_commercial_engine_quality_ok {passed(commercial_engine_report)}",
        "# HELP suplematch_lab_ocr_quality_ok Latest lab OCR quality report status.",
        "# TYPE suplematch_lab_ocr_quality_ok gauge",
        f"suplematch_lab_ocr_quality_ok {passed(ocr_report)}",
        "# HELP suplematch_scraping_validation_ok Latest scraping/catalog validation report status.",
        "# TYPE suplematch_scraping_validation_ok gauge",
        f"suplematch_scraping_validation_ok {passed(scraping_report)}",
        "# HELP suplematch_operational_quality_ok Latest operational quality suite status.",
        "# TYPE suplematch_operational_quality_ok gauge",
        f"suplematch_operational_quality_ok {passed(operational_report)}",
        "",
    ])


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
    scraping_report = _latest_json_report("data/reports/scraping/*catalog_validation_*.json")
    scraping_current_report = _read_json_report(BASE_DIR / "data/reports/scraping/catalog_pipeline_current_report.json")
    scraping_alert = _read_json_report(BASE_DIR / "data/reports/scraping/catalog_pipeline_alert.json")
    if scraping_current_report is not None:
        scraping_report = scraping_current_report
    model2_report = _read_json_report(BASE_DIR / "data/reports/supplement_model/01_model2_summary.json")
    commercial_engine_report = _read_json_report(BASE_DIR / "data/reports/commercial_engine/01_commercial_engine_summary.json")
    lab_ocr_report = _read_json_report(BASE_DIR / "data/reports/labs/01_ocr_lab_summary.json")
    operational_report = _read_json_report(BASE_DIR / "data/reports/operational/quality_summary.json")
    condition_golden_report = _latest_existing_report("data/reports/condition_model/*golden_summary*.csv")
    if scraping_report is not None:
        checks["scraping_validation_ok"] = scraping_report.get("status") == "passed"
    if model2_report is not None:
        checks["model2_quality_ok"] = model2_report.get("status") == "passed"
    if commercial_engine_report is not None:
        checks["commercial_engine_quality_ok"] = commercial_engine_report.get("status") == "passed"
    if lab_ocr_report is not None:
        checks["lab_ocr_quality_ok"] = lab_ocr_report.get("status") == "passed"
    if operational_report is not None:
        checks["operational_quality_ok"] = operational_report.get("status") == "passed"

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
        "scraping_validation": None if scraping_report is None else {
            "status": scraping_report.get("status"),
            "mode": scraping_report.get("mode"),
            "report_path": scraping_report.get("_path"),
            "raw_rows": (scraping_report.get("raw") or {}).get("rows"),
            "approved_rows": (scraping_report.get("approved") or {}).get("rows"),
            "approved_components": (scraping_report.get("approved") or {}).get("components"),
            "latest_scraped_at": ((scraping_report.get("raw") or {}).get("freshness") or {}).get("latest_scraped_at"),
            "age_hours": ((scraping_report.get("raw") or {}).get("freshness") or {}).get("age_hours"),
            "errors": scraping_report.get("errors") or [],
            "warnings": scraping_report.get("warnings") or [],
        },
        "scraping_alert": scraping_alert,
        "model2_quality": None if model2_report is None else {
            "status": model2_report.get("status"),
            "cases": model2_report.get("cases"),
            "top3_accuracy": model2_report.get("top3_accuracy"),
            "block_accuracy": model2_report.get("block_accuracy"),
            "commercial_coverage": model2_report.get("commercial_coverage"),
            "pharmacy_diversity": model2_report.get("pharmacy_diversity"),
            "summary_path": model2_report.get("summary_path"),
            "errors": model2_report.get("errors") or [],
        },
        "commercial_engine_quality": None if commercial_engine_report is None else {
            "status": commercial_engine_report.get("status"),
            "cases": commercial_engine_report.get("cases"),
            "passed": commercial_engine_report.get("passed"),
            "pass_rate": commercial_engine_report.get("pass_rate"),
            "summary_path": commercial_engine_report.get("summary_path"),
            "errors": commercial_engine_report.get("errors") or [],
        },
        "lab_ocr_quality": None if lab_ocr_report is None else {
            "status": lab_ocr_report.get("status"),
            "cases": lab_ocr_report.get("cases"),
            "recall": lab_ocr_report.get("recall"),
            "analytes": lab_ocr_report.get("analytes"),
            "analyte_recall": lab_ocr_report.get("analyte_recall"),
            "critical_accuracy": lab_ocr_report.get("critical_accuracy"),
            "avg_confidence": lab_ocr_report.get("avg_confidence"),
            "summary_path": lab_ocr_report.get("summary_path"),
            "errors": lab_ocr_report.get("errors") or [],
        },
        "operational_quality": None if operational_report is None else {
            "status": operational_report.get("status"),
            "generated_at": operational_report.get("generated_at"),
            "failed_required": operational_report.get("failed_required") or [],
            "failed_optional": operational_report.get("failed_optional") or [],
            "reports": operational_report.get("reports") or {},
        },
        "condition_model_quality": None if condition_golden_report is None else {
            "status": "available",
            "report_path": condition_golden_report.get("_path"),
        },
    }
