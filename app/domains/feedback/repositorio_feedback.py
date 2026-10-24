from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    CommercialProduct,
    RecommendationFeedback,
    RecommendationItem,
    RecommendationItemFeedback,
    RecommendationSession,
    RecommendedPack,
)
from app.domains.feedback.esquemas import FeedbackInput
from app.domains.feedback.contexto import build_context_key, build_item_context_key
from app.domains.feedback.recompensa import outcome_payload


class FeedbackRepository:
    def __init__(self, db: Session):
        self.db = db
        # component_id de item_ratings descartados en el ultimo save_feedback (no estaban en la recomendacion).
        self.last_ignored_item_ratings: list[str] = []

    def recommendation_exists(self, recommendation_id: str) -> bool:
        return (
            self.db.scalar(
                select(RecommendationSession.id).where(RecommendationSession.recommendation_id == recommendation_id)
            )
            is not None
        )

    def save_feedback(
        self,
        data: FeedbackInput,
        *,
        user_id: UUID | None = None,
    ) -> tuple[RecommendationFeedback, bool]:
        """Guarda o actualiza el feedback. Devuelve (feedback, created).

        Dedupe: un mismo usuario (o la misma sesion anonima) solo tiene un feedback por
        (recomendacion, pack); un segundo envio actualiza rating y comentario en vez de sumar un voto.
        """
        recommendation_session = self.db.scalar(
            select(RecommendationSession).where(
                RecommendationSession.recommendation_id == data.recommendation_id
            )
        )
        recommended_pack = None

        if recommendation_session is not None and data.pack_id:
            recommended_pack = self.db.scalar(
                select(RecommendedPack).where(
                    RecommendedPack.recommendation_session_id == recommendation_session.id,
                    RecommendedPack.pack_key == data.pack_id,
                )
            )

        rating = max(1, min(5, int(data.rating)))
        chosen_product_id = self._uuid_or_none(data.chosen_product_id)

        if recommendation_session is not None:
            existing_query = select(RecommendationFeedback).where(
                RecommendationFeedback.recommendation_session_id == recommendation_session.id,
                RecommendationFeedback.pack_key == data.pack_id,
            )
            existing_query = (
                existing_query.where(RecommendationFeedback.user_id == user_id)
                if user_id is not None
                else existing_query.where(RecommendationFeedback.user_id.is_(None))
            )
            existing = self.db.scalar(existing_query.order_by(RecommendationFeedback.created_at.desc()).limit(1))
            if existing is not None:
                existing.rating = rating
                existing.was_relevant = rating >= 3
                existing.would_follow = rating >= 4
                existing.comment = data.comment
                existing.component_ids_json = data.component_ids
                existing.selected_product_ids_json = data.selected_product_ids
                existing.chosen_product_id = chosen_product_id
                existing.product_context_json = data.product_context
                existing.conditions_context_json = data.conditions
                existing.context_key = build_context_key(data.pack_id, data.conditions)
                existing.outcome_json = outcome_payload(data)
                self._replace_item_ratings(existing, recommendation_session, data, user_id)
                self.db.commit()
                self.db.refresh(existing)
                return existing, False

        feedback = RecommendationFeedback(
            user_id=user_id,
            recommendation_session_id=recommendation_session.id if recommendation_session else None,
            recommended_pack_id=recommended_pack.id if recommended_pack else None,
            pack_key=data.pack_id,
            component_ids_json=data.component_ids,
            selected_product_ids_json=data.selected_product_ids,
            chosen_product_id=chosen_product_id,
            product_context_json=data.product_context,
            conditions_context_json=data.conditions,
            context_key=build_context_key(data.pack_id, data.conditions),
            outcome_json=outcome_payload(data),
            rating=rating,
            was_relevant=rating >= 3,
            would_follow=rating >= 4,
            comment=data.comment,
        )
        self.db.add(feedback)
        self._replace_item_ratings(feedback, recommendation_session, data, user_id)
        self.db.commit()
        self.db.refresh(feedback)
        return feedback, True

    def _replace_item_ratings(
        self,
        feedback: RecommendationFeedback,
        recommendation_session: RecommendationSession | None,
        data: FeedbackInput,
        user_id: UUID | None,
    ) -> list[str]:
        """Guarda las estrellas por suplemento. Devuelve los component_id ignorados.

        Con sesion conocida solo se aceptan suplementos que esa recomendacion mostro, y la condicion sale de
        `recommendation_items` (el cliente no la elige). Sin sesion (entornos que no exigen recomendacion
        conocida) la condicion queda vacia.
        """
        shown: dict[str, str | None] | None = None
        if recommendation_session is not None:
            shown = {
                str(external_id): condition
                for external_id, condition in self.db.execute(
                    select(RecommendationItem.external_component_id, RecommendationItem.condition_code).where(
                        RecommendationItem.recommendation_session_id == recommendation_session.id,
                        RecommendationItem.external_component_id.is_not(None),
                    )
                ).all()
            }
        feedback.item_ratings.clear()
        ignored: list[str] = []
        for item in data.item_ratings:
            if shown is not None and item.component_id not in shown:
                ignored.append(item.component_id)
                continue
            condition = shown.get(item.component_id) if shown is not None else None
            feedback.item_ratings.append(
                RecommendationItemFeedback(
                    user_id=user_id,
                    recommendation_session_id=recommendation_session.id if recommendation_session else None,
                    component_id=item.component_id,
                    condition_code=condition,
                    context_key=build_item_context_key(item.component_id, condition),
                    rating=item.rating,
                    outcome_json=outcome_payload(item),
                )
            )
        self.last_ignored_item_ratings = ignored
        return ignored

    def _uuid_or_none(self, value: str | None) -> UUID | None:
        if not value:
            return None
        try:
            parsed = UUID(str(value))
        except ValueError:
            return None
        exists = self.db.get(CommercialProduct, parsed)
        return parsed if exists is not None else None

    def summary(self, limit: int = 5) -> dict[str, Any]:
        total_feedback = self.db.scalar(select(func.count(RecommendationFeedback.id))) or 0

        grouped = self.db.execute(
            select(
                RecommendationFeedback.pack_key,
                func.count(RecommendationFeedback.id).label("feedback_count"),
                func.avg(RecommendationFeedback.rating).label("avg_rating"),
                func.max(RecommendationFeedback.created_at).label("last_feedback_at"),
            )
            .where(RecommendationFeedback.pack_key.is_not(None))
            .group_by(RecommendationFeedback.pack_key)
            .order_by(func.avg(RecommendationFeedback.rating).desc(), func.count(RecommendationFeedback.id).desc())
            .limit(limit)
        ).all()

        top_rated_packs = []
        for row in grouped:
            component_ids = self._latest_component_ids(row.pack_key)
            avg_rating = float(row.avg_rating or 0.0)
            top_rated_packs.append(
                {
                    "pack_id": row.pack_key,
                    "feedback_count": int(row.feedback_count or 0),
                    "avg_rating": round(avg_rating, 2),
                    "avg_score": round((avg_rating - 1.0) / 4.0, 4) if avg_rating else 0.0,
                    "component_ids": component_ids,
                    "last_feedback_at": row.last_feedback_at.isoformat() if row.last_feedback_at else None,
                }
            )

        return {
            "total_feedback_events": int(total_feedback),
            "packs_with_feedback": len(grouped),
            "top_rated_packs": top_rated_packs,
        }

    def _latest_component_ids(self, pack_key: str | None) -> list[str]:
        if pack_key is None:
            return []

        feedback = self.db.scalar(
            select(RecommendationFeedback)
            .where(RecommendationFeedback.pack_key == pack_key)
            .order_by(RecommendationFeedback.created_at.desc())
            .limit(1)
        )
        if feedback is None:
            return []

        return [str(component_id) for component_id in feedback.component_ids_json or [] if component_id]
