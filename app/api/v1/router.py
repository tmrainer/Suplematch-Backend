from fastapi import APIRouter

from app.api.v1.endpoints import health, debug, recommend, feedback

api_router = APIRouter()

api_router.include_router(health.router, tags=["Health"])
api_router.include_router(debug.router, prefix="/debug", tags=["Debug"])
api_router.include_router(recommend.router, prefix="/recommend", tags=["Recommendation"])
api_router.include_router(feedback.router, prefix="/feedback", tags=["Feedback"])
