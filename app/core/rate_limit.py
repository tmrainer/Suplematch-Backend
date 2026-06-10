from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


LIMITED_PREFIXES = (
    "/api/v1/auth",
    "/api/v1/feedback",
    "/api/v1/reviews",
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, enabled: bool, requests: int, window_seconds: int):
        super().__init__(app)
        self.enabled = enabled
        self.requests = requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if not self.enabled or not request.url.path.startswith(LIMITED_PREFIXES):
            return await call_next(request)

        now = time.monotonic()
        client = request.client.host if request.client else "unknown"
        key = f"{client}:{request.url.path}"
        hits = self._hits[key]
        cutoff = now - self.window_seconds
        while hits and hits[0] < cutoff:
            hits.popleft()

        if len(hits) >= self.requests:
            return JSONResponse(
                status_code=429,
                content={"detail": "Demasiadas solicitudes. Intenta nuevamente en unos minutos."},
            )

        hits.append(now)
        return await call_next(request)
