from uuid import uuid4

from sqlalchemy import select

from app.db.models import CommercialProduct, CommercialProductComponent, Component, Pharmacy, SupplementReview, User
from app.db.session import SessionLocal
from app.main import create_app
from app.domains.reviews.repositorio_metricas_resenas import ReviewMetricsRepository
from tests.integration.test_health import asgi_request


def test_pack_reviews_are_not_public_review_surface():
    app = create_app()

    status_code, body = asgi_request(app, "GET", "/api/v1/reviews/packs")

    assert status_code == 404
    assert body["detail"] == "Not Found"


def _register_user(app, email: str) -> str:
    status_code, body = asgi_request(
        app,
        "POST",
        "/api/v1/auth/register",
        {
            "email": email,
            "password": "Review123",
            "first_name": "Review",
            "last_name": "User",
            "age": 28,
            "weight_value": 70,
            "weight_unit": "kg",
            "height_value": 170,
            "height_unit": "cm",
        },
    )
    assert status_code == 200
    return body["access_token"]


def _create_product_fixture():
    with SessionLocal() as db:
        pharmacy = Pharmacy(name=f"Farmacia Review {uuid4().hex[:8]}", slug=f"review-{uuid4().hex[:8]}", active=True)
        component = Component(component_id=f"COMP_REVIEW_{uuid4().hex[:8]}", canonical_name="Componente review")
        db.add_all([pharmacy, component])
        db.flush()
        product = CommercialProduct(
            pharmacy_id=pharmacy.id,
            sku=f"sku-review-{uuid4().hex}",
            commercial_name="Producto review test",
            url="https://example.test/review-product",
            registro_sanitario="RS-REVIEW",
            price=35.0,
            currency="PEN",
            availability="available",
            commercial_status="active",
            raw_payload_json={},
        )
        db.add(product)
        db.flush()
        db.add(
            CommercialProductComponent(
                product_id=product.id,
                component_id=component.id,
                ingredient="Componente review",
                match_score=99.0,
            )
        )
        db.commit()
        return product.id, component.id, pharmacy.id


def _cleanup_product_fixture(product_id, component_id, pharmacy_id, email: str):
    with SessionLocal() as db:
        product = db.get(CommercialProduct, product_id)
        component = db.get(Component, component_id)
        pharmacy = db.get(Pharmacy, pharmacy_id)
        user = db.scalar(select(User).where(User.email == email))
        for item in (product, component, pharmacy, user):
            if item is not None:
                db.delete(item)
        db.commit()


def test_product_review_is_attached_to_commercial_product_and_derives_component():
    app = create_app()
    email = f"review-{uuid4().hex[:8]}@suplematch.test"
    token = _register_user(app, email)
    product_id, component_id, pharmacy_id = _create_product_fixture()

    try:
        status_code, body = asgi_request(
            app,
            "POST",
            "/api/v1/reviews/products",
            {
                "product_id": str(product_id),
                "rating": 5,
                "effectiveness_score": 4,
                "side_effects_score": 5,
                "price_value_score": 3,
                "comment": "Me pareció buen producto y el precio fue razonable.",
            },
            headers={"authorization": f"Bearer {token}"},
        )

        assert status_code == 200
        assert body["product_id"] == str(product_id)
        assert body["component_id"] == str(component_id)
        assert body["status"] == "pending"

        with SessionLocal() as db:
            review = db.scalar(select(SupplementReview).where(SupplementReview.product_id == product_id))
            assert review is not None
            assert review.component_id == component_id
    finally:
        _cleanup_product_fixture(product_id, component_id, pharmacy_id, email)


def test_product_review_metrics_use_product_level_scores_only():
    product_id, component_id, pharmacy_id = _create_product_fixture()
    try:
        with SessionLocal() as db:
            db.add_all([
                SupplementReview(
                    product_id=product_id,
                    component_id=component_id,
                    rating=5,
                    effectiveness_score=5,
                    side_effects_score=5,
                    price_value_score=4,
                    status="published",
                    verified_purchase=False,
                ),
                SupplementReview(
                    product_id=product_id,
                    component_id=component_id,
                    rating=4,
                    effectiveness_score=4,
                    side_effects_score=4,
                    price_value_score=5,
                    status="published",
                    verified_purchase=True,
                ),
            ])
            db.commit()

            metrics = ReviewMetricsRepository(db).product_metric(product_id)

            assert metrics["review_count"] == 2
            assert metrics["avg_rating"] == 4.5
            assert metrics["avg_effectiveness_score"] == 4.5
            assert metrics["avg_tolerance_score"] == 4.5
            assert metrics["avg_price_value_score"] == 4.5
            assert metrics["product_review_score"] > 0.70
            assert metrics["verified_review_ratio"] == 0.5
    finally:
        _cleanup_product_fixture(product_id, component_id, pharmacy_id, f"unused-{uuid4().hex}@test.local")


def test_quick_product_rating_is_published_and_updates_product_metrics():
    app = create_app()
    email = f"quick-review-{uuid4().hex[:8]}@suplematch.test"
    token = _register_user(app, email)
    product_id, component_id, pharmacy_id = _create_product_fixture()

    try:
        status_code, body = asgi_request(
            app,
            "POST",
            "/api/v1/reviews/products",
            {
                "product_id": str(product_id),
                "rating": 5,
                "effectiveness_score": 5,
                "price_value_score": 5,
                "source": "quick_recommendation",
            },
            headers={"authorization": f"Bearer {token}"},
        )

        assert status_code == 200
        assert body["status"] == "published"

        with SessionLocal() as db:
            metrics = ReviewMetricsRepository(db).product_metric(product_id)

        assert metrics["review_count"] == 1
        assert metrics["avg_rating"] == 5.0
        assert metrics["product_review_score"] > 0.70
    finally:
        _cleanup_product_fixture(product_id, component_id, pharmacy_id, email)
