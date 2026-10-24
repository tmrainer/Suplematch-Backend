"""Embudo de la encuesta: eventos por paso (ver, completar, enviar) y resumen de abandono.

Sirve para decidir con datos que preguntas sobran: donde abandona la gente y cuanto tarda cada paso. No guarda
respuestas de salud, solo la clave del paso y su posicion.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SurveyStepEvent, User

MAX_SURVEY_EVENTS_PER_BATCH = 100
SurveyEventType = Literal["view", "complete", "submit"]


class SurveyStepEventInput(BaseModel):
    survey_session_id: str = Field(min_length=8, max_length=80)
    step_key: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9_]+$")
    event_type: SurveyEventType
    position: int | None = Field(default=None, ge=0, le=200)
    visible_steps: int | None = Field(default=None, ge=0, le=200)
    contract_version: str | None = Field(default=None, max_length=20)


class SurveyStepEventsBatch(BaseModel):
    events: list[SurveyStepEventInput] = Field(min_length=1, max_length=MAX_SURVEY_EVENTS_PER_BATCH)


class SurveyStepEventsResult(BaseModel):
    status: str
    accepted: int


def save_survey_events(db: Session | None, batch: SurveyStepEventsBatch, user: User | None = None) -> dict:
    if db is None:
        return {"status": "not_persisted", "accepted": 0}
    for event in batch.events:
        db.add(SurveyStepEvent(user_id=user.id if user else None, **event.model_dump()))
    db.commit()
    return {"status": "ok", "accepted": len(batch.events)}


def funnel_summary(db: Session, days: int = 30) -> dict:
    """Por paso: sesiones que lo vieron, que lo completaron y que abandonaron ahi (ultimo paso visto sin enviar)."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = db.execute(
        select(
            SurveyStepEvent.survey_session_id,
            SurveyStepEvent.step_key,
            SurveyStepEvent.event_type,
            SurveyStepEvent.position,
            SurveyStepEvent.visible_steps,
            SurveyStepEvent.created_at,
        ).where(SurveyStepEvent.created_at >= since).order_by(SurveyStepEvent.created_at)
    ).all()

    viewed: dict[str, set[str]] = defaultdict(set)
    completed: dict[str, set[str]] = defaultdict(set)
    position: dict[str, list[int]] = defaultdict(list)
    last_view: dict[str, str] = {}
    submitted: set[str] = set()
    visible_steps: dict[str, int] = {}
    for session_id, step_key, event_type, pos, visible, _created in rows:
        if event_type == "submit":
            submitted.add(session_id)
            continue
        if event_type == "view":
            viewed[step_key].add(session_id)
            last_view[session_id] = step_key
            if pos is not None:
                position[step_key].append(pos)
        elif event_type == "complete":
            completed[step_key].add(session_id)
        if visible is not None:
            visible_steps[session_id] = visible

    abandoned: dict[str, int] = defaultdict(int)
    for session_id, step_key in last_view.items():
        if session_id not in submitted:
            abandoned[step_key] += 1

    sessions = set(last_view) | submitted
    steps = sorted(viewed, key=lambda key: (sum(position[key]) / len(position[key])) if position[key] else 999)
    return {
        "days": days,
        "sessions": len(sessions),
        "submitted": len(submitted),
        "completion_rate": round(len(submitted) / len(sessions), 4) if sessions else None,
        "avg_visible_steps": round(sum(visible_steps.values()) / len(visible_steps), 1) if visible_steps else None,
        "steps": [
            {
                "step_key": key,
                "viewed": len(viewed[key]),
                "completed": len(completed[key]),
                "abandoned_here": abandoned.get(key, 0),
                "drop_rate": round(abandoned.get(key, 0) / len(viewed[key]), 4) if viewed[key] else None,
            }
            for key in steps
        ],
    }
