from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import CommercialProduct, RecommendationSession, RecommendedPack, RecommendedPackItem


class SessionRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_for_user(self, user_id: UUID, limit: int = 50, offset: int = 0) -> list[RecommendationSession]:
        return list(
            self.db.scalars(
                select(RecommendationSession)
                .options(
                    selectinload(RecommendationSession.items),
                    selectinload(RecommendationSession.packs).selectinload(RecommendedPack.items),
                    selectinload(RecommendationSession.packs)
                    .selectinload(RecommendedPack.items)
                    .selectinload(RecommendedPackItem.product)
                    .selectinload(CommercialProduct.pharmacy),
                )
                .where(RecommendationSession.user_id == user_id)
                .order_by(RecommendationSession.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
        )

    def get_by_recommendation_id(self, recommendation_id: str) -> RecommendationSession | None:
        return self.db.scalar(
            select(RecommendationSession)
            .options(
                selectinload(RecommendationSession.items),
                selectinload(RecommendationSession.packs).selectinload(RecommendedPack.items),
                selectinload(RecommendationSession.packs)
                .selectinload(RecommendedPack.items)
                .selectinload(RecommendedPackItem.product)
                .selectinload(CommercialProduct.pharmacy),
            )
            .where(RecommendationSession.recommendation_id == recommendation_id)
        )


def session_conditions(session: RecommendationSession) -> list[str]:
    data = session.conditions_json or {}
    if isinstance(data, dict):
        conditions = data.get("conditions") or []
        return [str(item) for item in conditions]
    if isinstance(data, list):
        return [str(item) for item in data]
    return []


def pack_component_ids(pack: RecommendedPack) -> list[str]:
    return [item.external_component_id for item in pack.items if item.external_component_id]


def pack_component_names(pack: RecommendedPack) -> list[str]:
    return [item.component_name for item in pack.items if item.component_name]
