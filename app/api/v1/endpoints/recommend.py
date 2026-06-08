from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.v1.dependencies import db_session, optional_current_user
from app.core.errors import ModelNotLoadedError, RecommendationError, RecommendationGenerationError
from app.db.models import User
from app.schemas.encuesta import EncuestaInput
from app.schemas.recomendacion import RecommendationResponse
from app.services.recommendation_service import RecommendationService

router = APIRouter()


@router.post("", response_model=RecommendationResponse)
def recommend(
    data: EncuestaInput,
    request: Request,
    db: Session = Depends(db_session),
    user: User | None = Depends(optional_current_user),
):
    models = getattr(request.app.state, "models", None)

    if models is None:
        raise ModelNotLoadedError()

    try:
        service = RecommendationService(models=models, db=db)
        return service.recommend(data, user=user)
    except RecommendationError:
        raise
    except Exception as exc:
        raise RecommendationGenerationError() from exc
