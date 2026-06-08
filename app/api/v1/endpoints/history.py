from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.v1.dependencies import current_user, db_session
from app.db.models import RecommendedPack, RecommendationSession, User
from app.repositories.session_repository import (
    SessionRepository,
    pack_component_ids,
    pack_component_names,
    session_conditions,
)
from app.schemas.history import HistoryPackOut, RecommendationHistoryOut


router = APIRouter()


def _pack_out(pack: RecommendedPack) -> HistoryPackOut:
    return HistoryPackOut(
        id=pack.id,
        pack_key=pack.pack_key,
        rank=pack.rank,
        score_final=pack.score_final,
        score_gnn=pack.score_gnn,
        score_feedback=pack.score_feedback,
        score_reviews=pack.score_reviews,
        score_exposure=pack.score_exposure,
        score_products=pack.score_products,
        score_diversity=pack.score_diversity,
        component_ids=pack_component_ids(pack),
        component_names=pack_component_names(pack),
    )


def _session_out(session: RecommendationSession) -> RecommendationHistoryOut:
    packs = sorted(session.packs, key=lambda pack: pack.rank)
    return RecommendationHistoryOut(
        id=session.id,
        recommendation_id=session.recommendation_id,
        created_at=session.created_at,
        conditions=session_conditions(session),
        packs=[_pack_out(pack) for pack in packs],
    )


@router.get("/me", response_model=list[RecommendationHistoryOut])
def my_history(
    limit: int = 50,
    offset: int = 0,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    sessions = SessionRepository(db).list_for_user(user.id, limit=limit, offset=offset)
    return [_session_out(session) for session in sessions]


@router.get("/{recommendation_id}", response_model=RecommendationHistoryOut)
def recommendation_detail(
    recommendation_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    session = SessionRepository(db).get_by_recommendation_id(recommendation_id)
    if session is None or session.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recomendación no encontrada.")
    return _session_out(session)
