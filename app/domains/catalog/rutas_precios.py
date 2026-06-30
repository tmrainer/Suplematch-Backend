from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.dependencies import db_session
from app.domains.catalog.repositorio_catalogo import CatalogRepository


router = APIRouter()


@router.get("")
def search_prices(
    component_id: str | None = None,
    q: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(db_session),
):
    rows = CatalogRepository(db).search_products(
        component_id=component_id,
        query=q,
        limit=limit,
        offset=offset,
    )
    return [
        {
            "product_id": str(product.id),
            "pharmacy": pharmacy.name,
            "commercial_name": product.commercial_name,
            "brand": product.brand,
            "registro_sanitario": product.registro_sanitario,
            "price": product.price,
            "currency": product.currency,
            "availability": product.availability,
            "stock": product.stock,
            "url": product.url,
            "sku": product.sku,
            "last_seen_at": product.last_seen_at,
        }
        for product, pharmacy in rows
    ]
