from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.dependencies import db_session, optional_current_user, require_admin
from app.db.models import User
from app.domains.survey.contrato import survey_contract
from app.domains.survey.embudo import SurveyStepEventsBatch, SurveyStepEventsResult, funnel_summary, save_survey_events


router = APIRouter()
# Embudo de la encuesta, montado en /survey (el contrato sigue en /survey-contract).
events_router = APIRouter()


@router.get("")
def get_survey_contract():
    return survey_contract()


@events_router.post("/events", response_model=SurveyStepEventsResult)
def save_events(
    batch: SurveyStepEventsBatch,
    db: Session = Depends(db_session),
    user: User | None = Depends(optional_current_user),
):
    """Registra en lote (max 100) pasos vistos, completados y envios de la encuesta. No recibe respuestas."""
    return save_survey_events(db, batch, user=user)


@events_router.get("/funnel")
def get_funnel(
    days: int = Query(default=30, ge=1, le=365),
    _admin: User = Depends(require_admin),
    db: Session = Depends(db_session),
):
    """Abandono por paso en los ultimos `days` dias."""
    return funnel_summary(db, days=days)
