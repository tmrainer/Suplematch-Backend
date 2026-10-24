from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session

from app.db.models import AdminAction, CatalogRsReview, utcnow
from app.domains.admin.servicio_revision_rs import (
    REVIEW_STATUSES,
    STATUS_PENDING,
    is_valid_transition,
    normalize_rs_key,
)

# Campos descriptivos que se refrescan en cada carga mientras la fila siga `pending`.
_REFRESHABLE_FIELDS = (
    "url",
    "commercial_name",
    "digemid_producto",
    "digemid_composicion",
    "registro_sanitario_source",
    "match_reason",
    "sample_reason",
)


class CatalogRsReviewRepository:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ carga
    def upsert_items(self, items: Iterable[dict[str, Any]], *, dry_run: bool = False) -> dict[str, int]:
        """Inserta o refresca entradas de la cola sin pisar decisiones humanas.

        - Clave única: (pharmacy, sku, registro_sanitario_key).
        - Si la fila existe con status != pending no se toca (`skipped_decided`).
        - Si existe en pending se refrescan los campos descriptivos (`updated`).
        - Si no existe se inserta en pending (`inserted`).
        """
        items = list(items)
        stats = {"inserted": 0, "updated": 0, "skipped_decided": 0, "total": len(items)}
        if not items:
            return stats

        keys = [(item["pharmacy"], item["sku"], item["registro_sanitario_key"]) for item in items]
        existing: dict[tuple[str, str, str], CatalogRsReview] = {}
        chunk = 500
        for start in range(0, len(keys), chunk):
            rows = self.db.scalars(
                select(CatalogRsReview).where(
                    tuple_(
                        CatalogRsReview.pharmacy,
                        CatalogRsReview.sku,
                        CatalogRsReview.registro_sanitario_key,
                    ).in_(keys[start : start + chunk])
                )
            )
            for row in rows:
                existing[(row.pharmacy, row.sku, row.registro_sanitario_key)] = row

        for item, key in zip(items, keys):
            current = existing.get(key)
            if current is None:
                stats["inserted"] += 1
                if not dry_run:
                    self.db.add(CatalogRsReview(status=STATUS_PENDING, **item))
                continue
            if current.status != STATUS_PENDING:
                stats["skipped_decided"] += 1
                continue
            stats["updated"] += 1
            if not dry_run:
                for field in _REFRESHABLE_FIELDS:
                    setattr(current, field, item.get(field))
                current.updated_at = utcnow()
        if not dry_run:
            self.db.flush()
        return stats

    # ---------------------------------------------------------------- lectura
    def get(self, review_id: UUID | str) -> CatalogRsReview | None:
        return self.db.get(CatalogRsReview, review_id)

    def list_reviews(
        self,
        *,
        status: str | None = STATUS_PENDING,
        sample_reason: str | None = None,
        pharmacy: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[CatalogRsReview], int]:
        stmt = select(CatalogRsReview)
        count_stmt = select(func.count(CatalogRsReview.id))
        if status:
            stmt = stmt.where(CatalogRsReview.status == status)
            count_stmt = count_stmt.where(CatalogRsReview.status == status)
        if sample_reason:
            stmt = stmt.where(CatalogRsReview.sample_reason == sample_reason)
            count_stmt = count_stmt.where(CatalogRsReview.sample_reason == sample_reason)
        if pharmacy:
            stmt = stmt.where(CatalogRsReview.pharmacy == pharmacy)
            count_stmt = count_stmt.where(CatalogRsReview.pharmacy == pharmacy)
        stmt = stmt.order_by(
            CatalogRsReview.sample_reason.asc(),  # "inferred" antes que "random_sample"
            CatalogRsReview.pharmacy.asc(),
            CatalogRsReview.commercial_name.asc(),
            CatalogRsReview.created_at.asc(),
        )
        rows = list(self.db.scalars(stmt.offset(offset).limit(limit)))
        total = int(self.db.scalar(count_stmt) or 0)
        return rows, total

    def summary(self) -> dict[str, Any]:
        by_status = {status: 0 for status in REVIEW_STATUSES}
        by_sample_reason: dict[str, int] = {}
        by_status_and_reason: dict[str, dict[str, int]] = {}
        rows = self.db.execute(
            select(CatalogRsReview.status, CatalogRsReview.sample_reason, func.count(CatalogRsReview.id))
            .group_by(CatalogRsReview.status, CatalogRsReview.sample_reason)
        ).all()
        total = 0
        for status, sample_reason, count in rows:
            count = int(count or 0)
            total += count
            by_status[status] = by_status.get(status, 0) + count
            by_sample_reason[sample_reason] = by_sample_reason.get(sample_reason, 0) + count
            by_status_and_reason.setdefault(sample_reason, {})[status] = count
        decided = total - by_status.get(STATUS_PENDING, 0)
        return {
            "total": total,
            "pending": by_status.get(STATUS_PENDING, 0),
            "decided": decided,
            "progress": round(decided / total, 4) if total else 0.0,
            "by_status": by_status,
            "by_sample_reason": by_sample_reason,
            "by_sample_reason_and_status": by_status_and_reason,
        }

    def statuses_for_products(
        self,
        products: Iterable[tuple[str, str | None, str | None]],
    ) -> dict[tuple[str, str], str]:
        """Estado de revisión por (farmacia, sku) para el RS actual de cada producto.

        Solo cuenta la fila cuya `registro_sanitario_key` coincide con el RS que hoy
        tiene el producto: una decisión sobre un RS antiguo no afecta a uno nuevo.
        """
        wanted: dict[tuple[str, str, str], tuple[str, str]] = {}
        for pharmacy, sku, registro in products:
            rs_key = normalize_rs_key(registro)
            if not pharmacy or not sku or not rs_key:
                continue
            wanted[(pharmacy, sku, rs_key)] = (pharmacy, sku)
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
        return {wanted[(pharmacy, sku, rs_key)]: status for pharmacy, sku, rs_key, status in rows}

    # --------------------------------------------------------------- decisión
    def decide(
        self,
        review_id: UUID | str,
        *,
        status: str,
        reviewer_note: str | None,
        reviewer_user_id: UUID | None,
    ) -> CatalogRsReview:
        review = self.get(review_id)
        if review is None:
            raise LookupError("Entrada de revisión de RS no encontrada.")
        if not is_valid_transition(review.status, status):
            raise ValueError(f"Transición de estado no permitida: {review.status} -> {status}")

        before = {
            "status": review.status,
            "reviewer_note": review.reviewer_note,
            "reviewer_user_id": str(review.reviewer_user_id) if review.reviewer_user_id else None,
            "decided_at": review.decided_at.isoformat() if review.decided_at else None,
        }
        now = utcnow()
        review.status = status
        review.reviewer_note = reviewer_note
        review.reviewer_user_id = reviewer_user_id
        review.decided_at = None if status == STATUS_PENDING else now
        review.updated_at = now
        after = {
            "status": review.status,
            "reviewer_note": review.reviewer_note,
            "reviewer_user_id": str(reviewer_user_id) if reviewer_user_id else None,
            "decided_at": review.decided_at.isoformat() if review.decided_at else None,
            "pharmacy": review.pharmacy,
            "sku": review.sku,
            "registro_sanitario_key": review.registro_sanitario_key,
        }
        self.db.add(
            AdminAction(
                admin_user_id=reviewer_user_id,
                action_type="catalog_rs_review_decision",
                entity_type="catalog_rs_review",
                entity_id=str(review.id),
                before_json=before,
                after_json=after,
            )
        )
        self.db.flush()
        return review
