from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.v1.dependencies import current_user, db_session
from app.db.models import RecommendationItem, RecommendedPack, RecommendedPackItem, RecommendationSession, User
from app.repositories.session_repository import (
    SessionRepository,
    pack_component_ids,
    pack_component_names,
    session_conditions,
)
from app.schemas.history import (
    HistoryPackOut,
    HistoryRecommendationItemOut,
    HistorySelectedProductOut,
    RecommendationHistoryOut,
)


router = APIRouter()


def _item_out(item: RecommendationItem) -> HistoryRecommendationItemOut:
    return HistoryRecommendationItemOut(
        id=item.id,
        component_id=item.external_component_id,
        component_name=item.component_name,
        rank=item.rank,
        reason=item.reason,
        score_model=item.score_model,
        recommendation_type=item.recommendation_type,
        condition_code=item.condition_code,
    )


def _selected_product_out(item: RecommendedPackItem) -> HistorySelectedProductOut:
    product = item.product
    pharmacy = product.pharmacy.name if product is not None and product.pharmacy is not None else None
    return HistorySelectedProductOut(
        component_id=item.external_component_id,
        component_name=item.component_name,
        product_id=item.product_id,
        commercial_name=product.commercial_name if product is not None else None,
        pharmacy=pharmacy,
        url=product.url if product is not None else None,
        price_at_recommendation=item.price_at_recommendation,
        availability_at_recommendation=item.availability_at_recommendation,
        product_score=item.product_score,
        review_score=item.review_score,
        price_score=item.price_score,
        stock_score=item.stock_score,
        traceability_score=item.traceability_score,
        pharmacy_diversity_score=item.pharmacy_diversity_score,
        selection_metrics=item.selection_metrics_json or {},
    )


def _pack_out(pack: RecommendedPack) -> HistoryPackOut:
    pack_items = sorted(pack.items, key=lambda item: item.rank)
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
        selected_products=[
            _selected_product_out(item)
            for item in pack_items
            if item.product_id is not None or item.selection_metrics_json
        ],
    )


def _session_out(session: RecommendationSession) -> RecommendationHistoryOut:
    packs = sorted(session.packs, key=lambda pack: pack.rank)
    items = sorted(session.items, key=lambda item: item.rank)
    return RecommendationHistoryOut(
        id=session.id,
        recommendation_id=session.recommendation_id,
        created_at=session.created_at,
        conditions=session_conditions(session),
        profile_warnings=session.profile_warnings_json or [],
        items=[_item_out(item) for item in items],
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
