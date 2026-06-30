from __future__ import annotations

import json
import logging
import time
from collections import Counter
from dataclasses import dataclass, field
from threading import Lock
from uuid import uuid4
from datetime import datetime, timezone
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware


logger = logging.getLogger("suplematch.events")


@dataclass
class HttpMetrics:
    requests_total: int = 0
    duration_ms_total: float = 0.0
    by_route: Counter[tuple[str, str, int]] = field(default_factory=Counter)


class InMemoryMetrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._started_at = time.time()
        self._http = HttpMetrics()
        self._domain_events: Counter[tuple[str, str]] = Counter()

    def record_http_request(self, method: str, path: str, status_code: int, duration_ms: float) -> None:
        with self._lock:
            self._http.requests_total += 1
            self._http.duration_ms_total += duration_ms
            self._http.by_route[(method, path, status_code)] += 1

    def record_domain_event(self, event: str, status: str = "ok") -> None:
        with self._lock:
            self._domain_events[(event, status)] += 1

    def prometheus_text(self) -> str:
        with self._lock:
            uptime_seconds = max(time.time() - self._started_at, 0.0)
            total = self._http.requests_total
            duration_total = self._http.duration_ms_total
            avg_duration = duration_total / total if total else 0.0
            by_route = dict(self._http.by_route)
            domain_events = dict(self._domain_events)

        lines = [
            "# HELP suplematch_app_uptime_seconds Process uptime in seconds.",
            "# TYPE suplematch_app_uptime_seconds gauge",
            f"suplematch_app_uptime_seconds {uptime_seconds:.3f}",
            "# HELP suplematch_http_requests_total Total HTTP requests observed by the app.",
            "# TYPE suplematch_http_requests_total counter",
            f"suplematch_http_requests_total {total}",
            "# HELP suplematch_http_request_duration_ms_total Sum of HTTP request durations in milliseconds.",
            "# TYPE suplematch_http_request_duration_ms_total counter",
            f"suplematch_http_request_duration_ms_total {duration_total:.3f}",
            "# HELP suplematch_http_request_duration_ms_avg Average HTTP request duration in milliseconds.",
            "# TYPE suplematch_http_request_duration_ms_avg gauge",
            f"suplematch_http_request_duration_ms_avg {avg_duration:.3f}",
            "# HELP suplematch_http_requests_by_route_total HTTP requests grouped by method, path and status.",
            "# TYPE suplematch_http_requests_by_route_total counter",
        ]
        for (method, path, status_code), count in sorted(by_route.items()):
            safe_path = path.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(
                f'suplematch_http_requests_by_route_total{{method="{method}",path="{safe_path}",status="{status_code}"}} {count}'
            )
        lines.extend(
            [
                "# HELP suplematch_domain_events_total Domain events grouped by event and status.",
                "# TYPE suplematch_domain_events_total counter",
            ]
        )
        for (event, status), count in sorted(domain_events.items()):
            safe_event = event.replace("\\", "\\\\").replace('"', '\\"')
            safe_status = status.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(
                f'suplematch_domain_events_total{{event="{safe_event}",status="{safe_status}"}} {count}'
            )
        lines.append("")
        return "\n".join(lines)


metrics = InMemoryMetrics()


def log_event(event: str, **fields: Any) -> None:
    payload = {
        "event": event,
        "ts": datetime.now(timezone.utc).isoformat(),
        **fields,
    }
    logger.info(json.dumps(payload, default=str, ensure_ascii=False, sort_keys=True))


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = request.headers.get("x-request-id") or uuid4().hex
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            metrics.record_http_request(request.method, request.url.path, status_code, duration_ms)
            log_event(
                "http_request_completed",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                duration_ms=duration_ms,
            )
            try:
                response.headers["x-request-id"] = request_id
            except Exception:
                pass
