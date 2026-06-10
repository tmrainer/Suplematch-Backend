from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CatalogOverride, CommercialProduct, CommercialProductComponent, Component, Pharmacy


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

        overrides = self._latest_overrides([product.id for product, _link, _component, _pharmacy in rows])
        products = []
        for product, link, component, pharmacy in rows:
            override = overrides.get(product.id)
            if override and override.blocked:
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
                    "regulatory_status": product.component_traceable or "digemid_match",
                    "catalog_preferred": bool(override.preferred) if override else product.commercial_status == "preferred",
                    "catalog_blocked": bool(override.blocked) if override else product.commercial_status == "blocked",
                    "catalog_override_reason": override.reason if override else None,
                    "restriction_flags": (product.raw_payload_json or {}).get("restriction_flags") or [],
                    "restriction_flags_verified": (product.raw_payload_json or {}).get("restriction_flags_verified") or [],
                    "restriction_flags_inferred": (product.raw_payload_json or {}).get("restriction_flags_inferred") or [],
                    "label_verified_at": (product.raw_payload_json or {}).get("label_verified_at"),
                    "label_verification_source": (product.raw_payload_json or {}).get("label_verification_source"),
                    "last_seen_at": product.last_seen_at.isoformat() if product.last_seen_at else None,
                }
            )

        return products

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
        return [
            (product, pharmacy)
            for product, pharmacy in rows
            if not (overrides.get(product.id) and overrides[product.id].blocked)
        ]

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
