from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import RecommendationFeedback, RecommendationSession, RecommendedPack
from app.schemas.feedback import FeedbackInput


class FeedbackRepository:
    def __init__(self, db: Session):
        self.db = db

    def save_feedback(
        self,
        data: FeedbackInput,
        *,
        user_id: UUID | None = None,
    ) -> RecommendationFeedback:
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

        rating = int(data.rating)
        feedback = RecommendationFeedback(
            user_id=user_id,
            recommendation_session_id=recommendation_session.id if recommendation_session else None,
            recommended_pack_id=recommended_pack.id if recommended_pack else None,
            pack_key=data.pack_id,
            component_ids_json=data.component_ids,
            conditions_context_json=data.conditions,
            rating=rating,
            was_relevant=rating >= 3,
            would_follow=rating >= 4,
            comment=data.comment,
        )
        self.db.add(feedback)
        self.db.commit()
        self.db.refresh(feedback)
        return feedback

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
