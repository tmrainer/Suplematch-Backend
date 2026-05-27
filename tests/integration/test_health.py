import asyncio
import json
from typing import Any

from app.main import create_app


def asgi_request(app, method: str, path: str, json_body: dict[str, Any] | None = None):
    body = b""
    headers = [(b"host", b"testserver")]

    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        headers.append((b"content-type", b"application/json"))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "headers": headers,
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

    return status_code, json.loads(response_body.decode("utf-8"))


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
