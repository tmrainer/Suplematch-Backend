from __future__ import annotations

from typing import Any, Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CommercialProduct, RecommendationEvent, RecommendationSession
from app.domains.feedback.contexto import IMPRESSION_EVENT, build_context_key, dedupe_impressions, impression_key
from app.domains.feedback.esquemas import RecommendationEventInput


class RecommendationEventRepository:
    """Persistencia de `recommendation_events` (impresiones, clicks, compras, retencion)."""

    def __init__(self, db: Session):
        self.db = db
        self._session_cache: dict[str, RecommendationSession | None] = {}

    # ------------------------------------------------------------------ lectura
    def session_for(self, recommendation_id: str) -> RecommendationSession | None:
        if recommendation_id not in self._session_cache:
            self._session_cache[recommendation_id] = self.db.scalar(
                select(RecommendationSession).where(RecommendationSession.recommendation_id == recommendation_id)
            )
        return self._session_cache[recommendation_id]

    def existing_impression_keys(self, session_ids: Iterable[UUID]) -> set[tuple]:
        ids = [sid for sid in session_ids if sid is not None]
        if not ids:
            return set()
        rows = self.db.execute(
            select(
                RecommendationEvent.recommendation_session_id,
                RecommendationEvent.event_type,
                RecommendationEvent.pack_key,
                RecommendationEvent.product_id,
                RecommendationEvent.position,
            ).where(
                RecommendationEvent.recommendation_session_id.in_(ids),
                RecommendationEvent.event_type == IMPRESSION_EVENT,
            )
        ).all()
        return {
            (
                str(row[0]),
                str(row[1]),
                str(row[2]) if row[2] is not None else None,
                str(row[3]) if row[3] is not None else None,
                int(row[4]) if row[4] is not None else None,
            )
            for row in rows
        }

    # ------------------------------------------------------------------ escritura
    def save_events(
        self,
        events: list[RecommendationEventInput],
        *,
        user_id: UUID | None = None,
        anonymous_session_id: str | None = None,
    ) -> dict[str, Any]:
        """Guarda un lote. Las impresiones se deduplican por (sesion, tipo, pack_key, product_id, position).

        Devuelve {"accepted", "deduplicated", "event_ids"}. Hace commit.
        """
        session_ids = {
            session.id
            for session in (self.session_for(event.recommendation_id) for event in events)
            if session is not None
        }
        existing = self.existing_impression_keys(session_ids)

        def _session_ref(event: RecommendationEventInput):
            session = self.session_for(event.recommendation_id)
            return str(session.id) if session is not None else f"rec:{event.recommendation_id}"

        accepted, dropped = dedupe_impressions(events, existing_keys=existing, session_ref_for=_session_ref)

        rows: list[RecommendationEvent] = []
        for event in accepted:
            session = self.session_for(event.recommendation_id)
            conditions = list(event.conditions or []) or self._session_conditions(session)
            row = RecommendationEvent(
                recommendation_session_id=session.id if session is not None else None,
                user_id=user_id if user_id is not None else (session.user_id if session is not None else None),
                anonymous_session_id=anonymous_session_id
                or (session.anonymous_session_id if session is not None else None),
                event_type=event.event_type,
                pack_key=event.pack_key,
                component_id=event.component_id,
                product_id=self._product_uuid_or_none(event.product_id),
                position=event.position,
                conditions_context_json=conditions,
                context_key=build_context_key(event.pack_key, conditions),
                payload_json=dict(event.payload or {}),
            )
            if event.product_id and row.product_id is None:
                # Conservar el identificador externo aunque no sea un UUID del catalogo.
                row.payload_json = {**row.payload_json, "raw_product_id": str(event.product_id)}
            self.db.add(row)
            rows.append(row)

        self.db.commit()
        return {
            "accepted": len(rows),
            "deduplicated": dropped,
            "event_ids": [str(row.id) for row in rows],
        }

    def add_pack_impressions(
        self,
        *,
        session: RecommendationSession,
        packs: list[dict[str, Any]],
        conditions: list[str],
    ) -> list[RecommendationEvent]:
        """Registra una impresion por pack mostrado (con su rank) sin hacer commit; el caller commitea.

        Se llama desde RecommendationRepository.save_response para no depender del frontend.
        """
        rows: list[RecommendationEvent] = []
        seen: set[tuple] = set()
        for index, pack in enumerate(packs, start=1):
            if not isinstance(pack, dict):
                continue
            pack_key = str(pack.get("pack_id") or "").strip() or f"pack_{pack.get('rank') or index}"
            position = int(pack.get("rank") or index)
            event = {"event_type": IMPRESSION_EVENT, "pack_key": pack_key, "product_id": None, "position": position}
            key = impression_key(event, str(session.id))
            if key in seen:
                continue
            seen.add(key)
            row = RecommendationEvent(
                recommendation_session_id=session.id,
                user_id=session.user_id,
                anonymous_session_id=session.anonymous_session_id,
                event_type=IMPRESSION_EVENT,
                pack_key=pack_key,
                position=position,
                conditions_context_json=list(conditions or []),
                context_key=build_context_key(pack_key, conditions),
                payload_json={
                    "source": "backend",
                    "component_ids": [str(cid) for cid in pack.get("component_ids") or [] if cid],
                    "score_final": pack.get("score_final"),
                },
            )
            self.db.add(row)
            rows.append(row)
        return rows

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _session_conditions(session: RecommendationSession | None) -> list[str]:
        if session is None:
            return []
        payload = session.conditions_json or {}
        values = payload.get("conditions") if isinstance(payload, dict) else payload
        return [str(value) for value in (values or []) if value]

    def _product_uuid_or_none(self, value: str | None) -> UUID | None:
        if not value:
            return None
        try:
            parsed = UUID(str(value))
        except ValueError:
            return None
        return parsed if self.db.get(CommercialProduct, parsed) is not None else None
