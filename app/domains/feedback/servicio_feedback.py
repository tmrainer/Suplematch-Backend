from fastapi import HTTPException, status

from app.core.config import settings
from app.db.models import User
from app.domains.feedback.esquemas import FeedbackInput, RecommendationEventsBatch
from app.domains.feedback.recompensa import reward
from app.domains.feedback.repositorio_eventos import RecommendationEventRepository
from app.domains.feedback.repositorio_feedback import FeedbackRepository
from app.ml.runtime.feedback_store import get_feedback_summary, legacy_store_enabled, save_feedback_event


class FeedbackService:
    def __init__(self, db=None):
        self.db = db

    def save_feedback(self, data: FeedbackInput, user: User | None = None) -> dict:
        if self.db is not None:
            repository = FeedbackRepository(self.db)
            if settings.FEEDBACK_REQUIRE_KNOWN_RECOMMENDATION and not repository.recommendation_exists(data.recommendation_id):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="recommendation_id desconocido; el feedback debe referir a una recomendacion generada por el sistema.",
                )
            feedback, created = repository.save_feedback(data, user_id=user.id if user else None)
            return {
                "status": "saved" if created else "updated",
                "feedback_id": str(feedback.id),
                "recommendation_id": data.recommendation_id,
                "rating": data.rating,
                "reward": round(reward(data), 4),
                "context_key": feedback.context_key,
                "item_ratings_saved": len(feedback.item_ratings),
                "item_ratings_ignored": repository.last_ignored_item_ratings,
            }

        # Sin BD (demos locales): solo el store legado si esta habilitado explicitamente.
        if legacy_store_enabled():
            feedback_id = save_feedback_event(
                recommendation_id=data.recommendation_id,
                pack_id=data.pack_id,
                component_ids=data.component_ids,
                rating_overall=data.rating,
                conditions_context=data.conditions,
                comment=data.comment,
            )
            return {"status": "saved", "feedback_id": feedback_id, "recommendation_id": data.recommendation_id, "rating": data.rating}

        return {
            "status": "not_persisted",
            "feedback_id": None,
            "recommendation_id": data.recommendation_id,
            "rating": data.rating,
            "detail": "Sin base de datos configurada; el feedback no se guardo.",
        }

    def save_events(self, batch: RecommendationEventsBatch, user: User | None = None) -> dict:
        """Persiste un lote de eventos de interaccion (impresiones, clicks, compras, retencion)."""
        if self.db is None:
            return {
                "status": "not_persisted",
                "accepted": 0,
                "deduplicated": 0,
                "event_ids": [],
                "detail": "Sin base de datos configurada; los eventos no se guardaron.",
            }

        feedback_repository = FeedbackRepository(self.db)
        if settings.FEEDBACK_REQUIRE_KNOWN_RECOMMENDATION:
            unknown = sorted(
                {
                    event.recommendation_id
                    for event in batch.events
                    if not feedback_repository.recommendation_exists(event.recommendation_id)
                }
            )
            if unknown:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"recommendation_id desconocido: {', '.join(unknown[:5])}. Los eventos deben referir a recomendaciones generadas por el sistema.",
                )

        result = RecommendationEventRepository(self.db).save_events(
            batch.events,
            user_id=user.id if user else None,
            anonymous_session_id=batch.anonymous_session_id,
        )
        return {"status": "saved", **result}

    def summary(self) -> dict:
        if self.db is not None:
            return FeedbackRepository(self.db).summary()

        return get_feedback_summary()
