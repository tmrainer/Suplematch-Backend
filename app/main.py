from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import setup_exception_handlers
from app.core.observability import RequestLoggingMiddleware
from app.core.rate_limit import RateLimitMiddleware
from app.ml.model_loader import load_all_models


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.models = load_all_models()
    yield


def create_app() -> FastAPI:
    logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(
        RateLimitMiddleware,
        enabled=settings.RATE_LIMIT_ENABLED,
        requests=settings.RATE_LIMIT_REQUESTS,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
    )
    app.add_middleware(RequestLoggingMiddleware)

    setup_exception_handlers(app)

    app.include_router(api_router, prefix="/api/v1")

    return app


app = create_app()
