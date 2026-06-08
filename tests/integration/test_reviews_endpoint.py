from app.main import create_app
from tests.integration.test_health import asgi_request


def test_pack_reviews_are_not_public_review_surface():
    app = create_app()

    status_code, body = asgi_request(app, "GET", "/api/v1/reviews/packs")

    assert status_code == 404
    assert body["detail"] == "Not Found"
