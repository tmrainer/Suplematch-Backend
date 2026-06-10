from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.observability import log_event
from app.db.models import AdminAction, CatalogImportRun, CatalogOverride, CommercialProduct, Pharmacy
from app.schemas.admin import ProductAdminUpdate


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

        for product in products:
            payload = product.raw_payload_json or {}
            if payload.get("restriction_flags_verified"):
                with_verified_flags += 1
            if payload.get("restriction_flags_inferred"):
                with_inferred_flags += 1
            if payload.get("label_verification_source"):
                with_label_source += 1
            if payload.get("label_verified_at"):
                with_recent_label_review += 1

        traceability_rate = round(with_rs / total, 4) if total else 0.0
        verified_label_rate = round(with_label_source / total, 4) if total else 0.0
        warnings = []
        if total == 0:
            warnings.append("Catálogo vacío")
        if traceability_rate < 0.95:
            warnings.append("Menos del 95% del catálogo tiene registro sanitario informado")
        if verified_label_rate < 0.50:
            warnings.append("Pocas etiquetas tienen fuente de verificación registrada")
        if with_verified_flags == 0:
            warnings.append("No hay flags de restricciones verificados; se usan inferencias conservadoras")

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
            "warnings": warnings,
        }
