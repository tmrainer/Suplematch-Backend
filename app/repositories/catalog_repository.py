from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CommercialProduct, CommercialProductComponent, Component, Pharmacy


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
                CommercialProduct.commercial_status == "active",
                CommercialProduct.availability == "available",
                CommercialProduct.price.is_not(None),
            )
            .order_by(CommercialProduct.price.asc(), CommercialProductComponent.match_score.desc().nullslast())
            .limit(limit)
        ).all()

        products = []
        for product, link, component, pharmacy in rows:
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
            .where(CommercialProduct.commercial_status == "active")
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
        return list(self.db.execute(stmt.offset(offset).limit(limit)))
