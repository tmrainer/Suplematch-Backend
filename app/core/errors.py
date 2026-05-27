from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


logger = logging.getLogger(__name__)

RECOMMENDATION_ERROR_DETAIL = (
    "No se pudo generar la recomendación. Revisa los artefactos del modelo."
)
FEEDBACK_ERROR_DETAIL = "Feedback inválido. El rating debe estar entre 1 y 5."
VALIDATION_ERROR_DETAIL = "Datos inválidos. Revisa los campos enviados."


class ApiError(Exception):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    detail = "Ocurrió un error inesperado."

    def __init__(self, detail: str | None = None, status_code: int | None = None):
        if detail is not None:
            self.detail = detail

        if status_code is not None:
            self.status_code = status_code


class RecommendationError(ApiError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    detail = RECOMMENDATION_ERROR_DETAIL


class ModelNotLoadedError(RecommendationError):
    pass


class RecommendationGenerationError(RecommendationError):
    pass


async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    logger.warning("%s: %s", exc.__class__.__name__, exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    logger.info("Request validation error on %s: %s", request.url.path, exc.errors())

    detail = VALIDATION_ERROR_DETAIL

    if request.url.path.rstrip("/").endswith("/feedback"):
        detail = FEEDBACK_ERROR_DETAIL

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": detail},
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "Unhandled error on %s",
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Ocurrió un error inesperado."},
    )


def setup_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
