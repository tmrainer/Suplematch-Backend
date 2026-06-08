from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AdminAction, CatalogImportRun, CatalogOverride, CommercialProduct, Pharmacy
from app.schemas.admin import ProductAdminUpdate


class AdminRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_products(self, *, limit: int = 100, offset: int = 0, status: str | None = None) -> list[tuple[CommercialProduct, Pharmacy]]:
        query = (
            select(CommercialProduct, Pharmacy)
            .join(Pharmacy, CommercialProduct.pharmacy_id == Pharmacy.id)
            .order_by(CommercialProduct.updated_at.desc())
        )
        if status:
            query = query.where(CommercialProduct.commercial_status == status)
        return list(self.db.execute(query.offset(offset).limit(limit)))

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
            "preferred": None,
            "blocked": None,
        }
        values = data.model_dump(exclude_unset=True)
        if values.get("status") is not None:
            product.commercial_status = values["status"]

        override = CatalogOverride(
            product_id=product.id,
            status=values.get("status"),
            preferred=bool(values.get("preferred", False)),
            blocked=bool(values.get("blocked", False)),
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
        return product

    def list_import_runs(self, limit: int = 50, offset: int = 0) -> list[CatalogImportRun]:
        return list(
            self.db.scalars(
                select(CatalogImportRun)
                .order_by(CatalogImportRun.started_at.desc())
                .offset(offset)
                .limit(limit)
            )
        )
