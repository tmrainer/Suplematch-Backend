from fastapi import APIRouter

from app.api.v1.endpoints import debug, health
from app.domains.admin import rutas as admin
from app.domains.auth import rutas as auth
from app.domains.catalog import rutas_componentes as components
from app.domains.catalog import rutas_precios as prices
from app.domains.feedback import rutas as feedback
from app.domains.history import rutas as history
from app.domains.labs import rutas as labs
from app.domains.recommendations import rutas as recommend
from app.domains.reviews import rutas as reviews
from app.domains.survey import rutas as survey_contract
from app.domains.users import rutas as users

api_router = APIRouter()

api_router.include_router(health.router, tags=["Health"])
api_router.include_router(debug.router, prefix="/debug", tags=["Debug"])
api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(components.router, prefix="/components", tags=["Components"])
api_router.include_router(prices.router, prefix="/prices", tags=["Prices"])
api_router.include_router(recommend.router, prefix="/recommend", tags=["Recommendation"])
api_router.include_router(survey_contract.router, prefix="/survey-contract", tags=["Survey"])
api_router.include_router(feedback.router, prefix="/feedback", tags=["Feedback"])
api_router.include_router(history.router, prefix="/history", tags=["History"])
api_router.include_router(labs.router, prefix="/labs", tags=["Labs"])
api_router.include_router(reviews.router, prefix="/reviews", tags=["Reviews"])
api_router.include_router(admin.router, prefix="/admin", tags=["Admin"])
