from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import BASE_DIR
from app.core.observability import log_event
from app.db.models import AdminAction, CatalogImportRun, CatalogOverride, CommercialProduct, Pharmacy
from app.domains.admin.esquemas import ProductAdminUpdate


CATALOG_REJECTIONS_PATH = BASE_DIR / "data/reports/catalog/approved_catalog_rejections.csv"
MISSING_COMPONENT_DEMAND_PATH = BASE_DIR / "data/reports/catalog/missing_component_demand.csv"


class AdminRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_products(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        status: str | None = None,
    ) -> list[tuple[CommercialProduct, Pharmacy, CatalogOverride | None]]:
        query = (
            select(CommercialProduct, Pharmacy)
            .join(Pharmacy, CommercialProduct.pharmacy_id == Pharmacy.id)
            .order_by(CommercialProduct.updated_at.desc())
        )
        if status:
            if status == "preferred":
                preferred_ids = select(CatalogOverride.product_id).where(CatalogOverride.preferred.is_(True))
                query = query.where(CommercialProduct.id.in_(preferred_ids))
            else:
                query = query.where(CommercialProduct.commercial_status == status)

        rows = list(self.db.execute(query.offset(offset).limit(limit)))
        overrides = self._latest_overrides([product.id for product, _pharmacy in rows])
        return [(product, pharmacy, overrides.get(product.id)) for product, pharmacy in rows]

    def update_product(
        self,
        product_id: UUID | str,
        data: ProductAdminUpdate,
        *,
        admin_user_id: UUID | None,
    ) -> CommercialProduct | None:
        product = self.db.get(CommercialProduct, product_id)
        if product is None:
            return None

        before = {
            "commercial_status": product.commercial_status,
            "preferred": False,
            "blocked": product.commercial_status == "blocked",
        }
        values = data.model_dump(exclude_unset=True)
        blocked = bool(values.get("blocked", False))
        preferred = bool(values.get("preferred", False))
        status = values.get("status")

        if blocked:
            product.commercial_status = "blocked"
            status = "blocked"
            preferred = False
        elif status is not None:
            product.commercial_status = status
        elif preferred and product.commercial_status not in {"active", "inactive"}:
            product.commercial_status = "active"

        override = CatalogOverride(
            product_id=product.id,
            status=status,
            preferred=preferred,
            blocked=blocked,
            reason=values.get("reason"),
            admin_user_id=admin_user_id,
        )
        self.db.add(override)
        self.db.add(
            AdminAction(
                admin_user_id=admin_user_id,
                action_type="update_product",
                entity_type="commercial_product",
                entity_id=str(product.id),
                before_json=before,
                after_json=values,
            )
        )
        self.db.commit()
        self.db.refresh(product)
        log_event(
            "admin_product_updated",
            product_id=str(product.id),
            admin_user_id=str(admin_user_id) if admin_user_id else None,
            commercial_status=product.commercial_status,
            preferred=preferred,
            blocked=blocked,
            reason=values.get("reason"),
        )
        return product

    def latest_override(self, product_id: UUID | str) -> CatalogOverride | None:
        return self.db.scalar(
            select(CatalogOverride)
            .where(CatalogOverride.product_id == product_id)
            .order_by(CatalogOverride.created_at.desc())
            .limit(1)
        )

    def _latest_overrides(self, product_ids: list[UUID]) -> dict[UUID, CatalogOverride]:
        if not product_ids:
            return {}

        rows = list(
            self.db.scalars(
                select(CatalogOverride)
                .where(CatalogOverride.product_id.in_(product_ids))
                .order_by(CatalogOverride.product_id.asc(), CatalogOverride.created_at.desc())
            )
        )
        overrides: dict[UUID, CatalogOverride] = {}
        for override in rows:
            overrides.setdefault(override.product_id, override)
        return overrides

    def list_import_runs(self, limit: int = 50, offset: int = 0) -> list[CatalogImportRun]:
        return list(
            self.db.scalars(
                select(CatalogImportRun)
                .order_by(CatalogImportRun.started_at.desc())
                .offset(offset)
                .limit(limit)
            )
        )

    def catalog_quality_summary(self) -> dict:
        products = list(self.db.scalars(select(CommercialProduct)))
        total = len(products)
        active = sum(1 for product in products if product.commercial_status in {"active", "preferred"})
        with_rs = sum(1 for product in products if product.registro_sanitario)
        with_verified_flags = 0
        with_inferred_flags = 0
        with_label_source = 0
        with_recent_label_review = 0
        without_rs = 0
        with_digemid_name_match = 0
        with_image_ocr_rs = 0
        low_confidence = 0
        medium_confidence = 0
        high_confidence = 0

        for product in products:
            payload = product.raw_payload_json or {}
            if not product.registro_sanitario:
                without_rs += 1
            if payload.get("registro_sanitario_source") == "digemid_name_match":
                with_digemid_name_match += 1
            if payload.get("registro_sanitario_source") == "image_ocr":
                with_image_ocr_rs += 1
            if payload.get("restriction_flags_verified"):
                with_verified_flags += 1
            if payload.get("restriction_flags_inferred"):
                with_inferred_flags += 1
            if payload.get("label_verification_source"):
                with_label_source += 1
            if payload.get("label_verified_at"):
                with_recent_label_review += 1
            level = str(payload.get("commercial_confidence_level") or "").lower()
            if level == "alta":
                high_confidence += 1
            elif level == "media":
                medium_confidence += 1
            elif level == "baja":
                low_confidence += 1

        traceability_rate = round(with_rs / total, 4) if total else 0.0
        verified_label_rate = round(with_label_source / total, 4) if total else 0.0
        rejected_by_reason, rejected_by_pharmacy = self._catalog_rejection_counters(CATALOG_REJECTIONS_PATH)
        missing_components, weak_components = self._component_demand_rows(MISSING_COMPONENT_DEMAND_PATH)
        warnings = []
        if total == 0:
            warnings.append("Catálogo vacío")
        if traceability_rate < 0.95:
            warnings.append("Menos del 95% del catálogo tiene registro sanitario informado")
        if verified_label_rate < 0.50:
            warnings.append("Pocas etiquetas tienen fuente de verificación registrada")
        if with_verified_flags == 0:
            warnings.append("No hay flags de restricciones verificados; se usan inferencias conservadoras")
        if missing_components:
            warnings.append("Hay componentes recomendables sin producto comercial validado")
        if weak_components:
            warnings.append("Hay componentes con baja rotación comercial")

        return {
            "products_total": total,
            "active_products": active,
            "products_with_registro_sanitario": with_rs,
            "products_with_verified_restriction_flags": with_verified_flags,
            "products_with_inferred_restriction_flags": with_inferred_flags,
            "products_with_label_source": with_label_source,
            "products_with_recent_label_review": with_recent_label_review,
            "traceability_rate": traceability_rate,
            "verified_label_rate": verified_label_rate,
            "products_without_registro_sanitario": without_rs,
            "products_with_digemid_name_match": with_digemid_name_match,
            "products_with_image_ocr_rs": with_image_ocr_rs,
            "products_with_low_commercial_confidence": low_confidence,
            "products_with_medium_commercial_confidence": medium_confidence,
            "products_with_high_commercial_confidence": high_confidence,
            "rejected_by_reason": rejected_by_reason,
            "rejected_by_pharmacy": rejected_by_pharmacy,
            "components_missing_product": missing_components,
            "components_weak_product": weak_components,
            "warnings": warnings,
        }

    def _catalog_rejection_counters(self, path: Path) -> tuple[dict[str, int], dict[str, int]]:
        if not path.exists():
            return {}, {}
        by_reason: Counter[str] = Counter()
        by_pharmacy: Counter[str] = Counter()
        with path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                reason = str(row.get("catalog_rejection_reason") or "unknown").strip() or "unknown"
                pharmacy = str(row.get("pharmacy") or "unknown").strip() or "unknown"
                by_reason[reason] += 1
                by_pharmacy[pharmacy] += 1
        return dict(by_reason.most_common(12)), dict(by_pharmacy.most_common(12))

    def _component_demand_rows(self, path: Path) -> tuple[list[dict], list[dict]]:
        if not path.exists():
            return [], []
        missing: list[dict] = []
        weak: list[dict] = []
        with path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                item = {
                    "component_id": row.get("component_id", ""),
                    "component_name": row.get("component_name", ""),
                    "safe_rotation_products": row.get("safe_rotation_products", ""),
                    "distinct_pharmacies": row.get("distinct_pharmacies", ""),
                    "reason": row.get("reason", ""),
                    "next_action": row.get("next_action", ""),
                    "search_terms": row.get("search_terms", ""),
                }
                if row.get("demand_status") == "missing":
                    missing.append(item)
                elif row.get("demand_status") == "weak":
                    weak.append(item)
        return missing[:20], weak[:20]
