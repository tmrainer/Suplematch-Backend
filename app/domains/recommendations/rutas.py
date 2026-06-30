from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.v1.dependencies import current_user, db_session
from app.core.errors import ModelNotLoadedError, RecommendationError, RecommendationGenerationError
from app.db.models import User
from app.domains.survey.esquemas_encuesta import EncuestaInput
from app.domains.recommendations.esquemas import RecommendationResponse
from app.domains.recommendations.servicio_recomendaciones import RecommendationService

router = APIRouter()


@router.post("", response_model=RecommendationResponse, response_model_exclude_none=True)
def recommend(
    data: EncuestaInput,
    request: Request,
    db: Session = Depends(db_session),
    user: User = Depends(current_user),
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
