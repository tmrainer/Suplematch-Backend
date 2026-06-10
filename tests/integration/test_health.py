import asyncio
import json
from typing import Any

from app.main import create_app


def asgi_request(
    app,
    method: str,
    path: str,
    json_body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    parse_json: bool = True,
):
    body = b""
    raw_headers = [(b"host", b"testserver")]

    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        raw_headers.append((b"content-type", b"application/json"))

    for key, value in (headers or {}).items():
        raw_headers.append((key.lower().encode("latin-1"), value.encode("latin-1")))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "headers": raw_headers,
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }
    messages = []
    request_sent = False

    async def receive():
        nonlocal request_sent
        if request_sent:
            return {"type": "http.disconnect"}

        request_sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        messages.append(message)

    asyncio.run(app(scope, receive, send))

    status_code = 500
    response_body = b""

    for message in messages:
        if message["type"] == "http.response.start":
            status_code = message["status"]
        elif message["type"] == "http.response.body":
            response_body += message.get("body", b"")

    decoded_body = response_body.decode("utf-8")
    return status_code, json.loads(decoded_body) if parse_json else decoded_body


def test_health_endpoint_returns_ok():
    app = create_app()

    status_code, body = asgi_request(app, "GET", "/api/v1/health")

    assert status_code == 200
    assert body == {"status": "ok"}


def test_model_status_endpoint_returns_loaded_flags():
    app = create_app()
    app.state.models = {"pipeline_vitaminas": object()}

    status_code, body = asgi_request(app, "GET", "/api/v1/debug/model-status")

    assert status_code == 200
    assert body == {"models": {"pipeline_vitaminas": True}}


def test_survey_contract_endpoint_returns_versioned_enums():
    app = create_app()

    status_code, body = asgi_request(app, "GET", "/api/v1/survey-contract")

    assert status_code == 200
    assert body["version"]
    assert "tipo_dieta" in body["enums"]
    assert "condiciones_seguridad" in body["rules"]["hard_safety_values"]


def test_readiness_endpoint_returns_checks():
    app = create_app()
    app.state.models = {"pipeline_vitaminas": object()}

    status_code, body = asgi_request(app, "GET", "/api/v1/health/ready")

    assert status_code == 200
    assert body["status"] in {"ready", "degraded"}
    assert "db" in body["checks"]
    assert "alembic_head" in body["checks"]
    assert "models" in body["checks"]
    assert "catalog_products" in body["checks"]


def test_operational_health_endpoint_returns_aggregate_metrics():
    app = create_app()
    app.state.models = {"pipeline_vitaminas": object()}

    status_code, body = asgi_request(app, "GET", "/api/v1/health/ops")

    assert status_code == 200
    assert body["status"] in {"ok", "attention"}
    assert "generated_at" in body
    assert "catalog" in body
    assert "recommendations" in body
    assert "feedback" in body
    assert "reviews" in body
    assert "admin" in body
    assert "models_loaded" in body["checks"]


def test_metrics_endpoint_returns_prometheus_text():
    app = create_app()

    health_status, _ = asgi_request(app, "GET", "/api/v1/health")
    status_code, body = asgi_request(app, "GET", "/api/v1/metrics", parse_json=False)

    assert health_status == 200
    assert status_code == 200
    assert "suplematch_app_uptime_seconds" in body
    assert "suplematch_http_requests_total" in body
    assert 'path="/api/v1/health"' in body
