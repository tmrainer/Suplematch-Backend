from fastapi import APIRouter, Request

from app.core.errors import ModelNotLoadedError, RecommendationError, RecommendationGenerationError
from app.schemas.encuesta import EncuestaInput
from app.schemas.recomendacion import RecommendationResponse
from app.services.recommendation_service import RecommendationService

router = APIRouter()


@router.post("", response_model=RecommendationResponse)
def recommend(data: EncuestaInput, request: Request):
    models = getattr(request.app.state, "models", None)

    if models is None:
        raise ModelNotLoadedError()

    try:
        service = RecommendationService(models=models)
        return service.recommend(data)
    except RecommendationError:
        raise
    except Exception as exc:
        raise RecommendationGenerationError() from exc
