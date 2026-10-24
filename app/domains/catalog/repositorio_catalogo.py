from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session

from app.db.models import (
    CatalogOverride,
    CatalogRsReview,
    CommercialProduct,
    CommercialProductComponent,
    Component,
    Pharmacy,
)

# Estados de la cola de revisión de RS (docs/catalog_rs_review.md). Un producto
# cuyo RS actual fue rechazado por un revisor no se sirve; el resto se sirve y
# expone `rs_review_status` para que el cliente pueda mostrar la trazabilidad.
RS_REVIEW_REJECTED = "rejected"
RS_REVIEW_NOT_REQUIRED = "not_required"


class CatalogRepository:
    def __init__(self, db: Session):
        self.db = db

    def products_for_component(self, component_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.db.execute(
            select(CommercialProduct, CommercialProductComponent, Component, Pharmacy)
            .join(CommercialProductComponent, CommercialProductComponent.product_id == CommercialProduct.id)
            .join(Component, CommercialProductComponent.component_id == Component.id)
            .join(Pharmacy, CommercialProduct.pharmacy_id == Pharmacy.id)
            .where(
                Component.component_id == component_id,
                CommercialProduct.commercial_status.in_(["active", "preferred"]),
                CommercialProduct.availability == "available",
                CommercialProduct.price.is_not(None),
            )
            .order_by(CommercialProduct.price.asc(), CommercialProductComponent.match_score.desc().nullslast())
            .limit(limit)
        ).all()

        product_ids = [product.id for product, _link, _component, _pharmacy in rows]
        overrides = self._latest_overrides(product_ids)
        component_counts = self._component_counts(product_ids)
        rs_review_statuses = self._rs_review_statuses(
            [(pharmacy.name, product.sku, product.registro_sanitario) for product, _link, _component, pharmacy in rows]
        )
        products = []
        for product, link, component, pharmacy in rows:
            override = overrides.get(product.id)
            if override and override.blocked:
                continue
            rs_review_status = rs_review_statuses.get((pharmacy.name, product.sku or ""), RS_REVIEW_NOT_REQUIRED)
            if rs_review_status == RS_REVIEW_REJECTED:
                continue

            products.append(
                {
                    "product_id": str(product.id),
                    "pharmacy": pharmacy.name,
                    "commercial_name": product.commercial_name,
                    "formal_name": product.formal_name,
                    "registro_sanitario": product.registro_sanitario or "",
                    "digemid_producto": product.formal_name,
                    "component_id": component.component_id,
                    "ingredient": link.ingredient or component.canonical_name,
                    "amount": link.amount,
                    "unit": link.unit,
                    "amount_mg": link.amount_mg,
                    "component_match_score": link.match_score,
                    "price": float(product.price or 0),
                    "currency": product.currency,
                    "availability": product.availability,
                    "stock": product.stock,
                    "url": product.url,
                    "sku": product.sku,
                    "brand": product.brand,
                    "image_url": (product.raw_payload_json or {}).get("image_url"),
                    "image_source": (product.raw_payload_json or {}).get("image_source"),
                    "image_local_path": (product.raw_payload_json or {}).get("image_local_path"),
                    "regulatory_status": product.component_traceable or "digemid_match",
                    "rs_review_status": rs_review_status,
                    "catalog_preferred": bool(override.preferred) if override else product.commercial_status == "preferred",
                    "catalog_blocked": bool(override.blocked) if override else product.commercial_status == "blocked",
                    "catalog_override_reason": override.reason if override else None,
                    "product_component_count": component_counts.get(product.id, 1),
                    "restriction_flags": (product.raw_payload_json or {}).get("restriction_flags") or [],
                    "restriction_flags_verified": (product.raw_payload_json or {}).get("restriction_flags_verified") or [],
                    "restriction_flags_inferred": (product.raw_payload_json or {}).get("restriction_flags_inferred") or [],
                    "label_verified_at": (product.raw_payload_json or {}).get("label_verified_at"),
                    "label_verification_source": (product.raw_payload_json or {}).get("label_verification_source"),
                    "commercial_confidence_score": (product.raw_payload_json or {}).get("commercial_confidence_score"),
                    "commercial_confidence_level": (product.raw_payload_json or {}).get("commercial_confidence_level"),
                    "commercial_confidence_reasons": (product.raw_payload_json or {}).get("commercial_confidence_reasons"),
                    "last_seen_at": product.last_seen_at.isoformat() if product.last_seen_at else None,
                }
            )

        return products

    def _component_counts(self, product_ids: list) -> dict:
        if not product_ids:
            return {}
        rows = self.db.execute(
            select(CommercialProductComponent.product_id, func.count(CommercialProductComponent.id))
            .where(CommercialProductComponent.product_id.in_(product_ids))
            .group_by(CommercialProductComponent.product_id)
        ).all()
        return {product_id: int(count or 1) for product_id, count in rows}

    def list_components(self, limit: int = 100, offset: int = 0, query: str | None = None) -> list[Component]:
        stmt = select(Component).order_by(Component.canonical_name.asc())
        if query:
            stmt = stmt.where(Component.canonical_name.ilike(f"%{query}%"))
        return list(self.db.scalars(stmt.offset(offset).limit(limit)))

    def search_products(
        self,
        *,
        component_id: str | None = None,
        query: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[tuple[CommercialProduct, Pharmacy]]:
        stmt = (
            select(CommercialProduct, Pharmacy)
            .join(Pharmacy, CommercialProduct.pharmacy_id == Pharmacy.id)
            .where(CommercialProduct.commercial_status.in_(["active", "preferred"]))
            .order_by(CommercialProduct.price.asc().nullslast(), CommercialProduct.updated_at.desc())
        )
        if query:
            stmt = stmt.where(CommercialProduct.commercial_name.ilike(f"%{query}%"))
        if component_id:
            stmt = (
                stmt.join(CommercialProductComponent, CommercialProductComponent.product_id == CommercialProduct.id)
                .join(Component, CommercialProductComponent.component_id == Component.id)
                .where(Component.component_id == component_id)
            )
        rows = list(self.db.execute(stmt.offset(offset).limit(limit)))
        overrides = self._latest_overrides([product.id for product, _pharmacy in rows])
        rs_review_statuses = self._rs_review_statuses(
            [(pharmacy.name, product.sku, product.registro_sanitario) for product, pharmacy in rows]
        )
        return [
            (product, pharmacy)
            for product, pharmacy in rows
            if not (overrides.get(product.id) and overrides[product.id].blocked)
            and rs_review_statuses.get((pharmacy.name, product.sku or "")) != RS_REVIEW_REJECTED
        ]

    def _rs_review_statuses(self, products: list[tuple[str, str | None, str | None]]) -> dict[tuple[str, str], str]:
        """Estado de revisión humana del RS actual de cada producto, por (farmacia, sku).

        Solo aplica la fila de `catalog_rs_reviews` cuya clave de RS coincide con el RS
        que hoy tiene el producto (normalizado: 'DE-1230' == 'DE1230'); una decisión
        sobre un RS anterior no arrastra al nuevo. Sin fila -> `not_required`.
        """
        wanted: dict[tuple[str, str, str], tuple[str, str]] = {}
        for pharmacy_name, sku, registro in products:
            rs_key = re.sub(r"[^A-Z0-9]", "", str(registro or "").upper())
            if not pharmacy_name or not sku or not rs_key:
                continue
            wanted[(pharmacy_name, sku, rs_key)] = (pharmacy_name, sku)
        if not wanted:
            return {}
        rows = self.db.execute(
            select(
                CatalogRsReview.pharmacy,
                CatalogRsReview.sku,
                CatalogRsReview.registro_sanitario_key,
                CatalogRsReview.status,
            ).where(
                tuple_(
                    CatalogRsReview.pharmacy,
                    CatalogRsReview.sku,
                    CatalogRsReview.registro_sanitario_key,
                ).in_(list(wanted))
            )
        ).all()
        return {wanted[(pharmacy_name, sku, rs_key)]: status for pharmacy_name, sku, rs_key, status in rows}

    def _latest_overrides(self, product_ids: list) -> dict:
        if not product_ids:
            return {}

        rows = list(
            self.db.scalars(
                select(CatalogOverride)
                .where(CatalogOverride.product_id.in_(product_ids))
                .order_by(CatalogOverride.product_id.asc(), CatalogOverride.created_at.desc())
            )
        )
        overrides = {}
        for override in rows:
            overrides.setdefault(override.product_id, override)
        return overrides
