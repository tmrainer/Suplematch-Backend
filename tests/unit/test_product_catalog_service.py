import csv

import app.services.product_catalog_service as product_catalog_module
from app.services.product_catalog_service import ProductCatalogService, _catalog_by_component


def _write_catalog(path):
    rows = [
        {
            "pharmacy": "Inkafarma",
            "commercial_name": "Vitamina D A",
            "formal_name": "Vitamina D",
            "registro_sanitario": "DE-1",
            "digemid_producto": "VITAMINA D",
            "component_id": "cmp_vit_d",
            "ingredient": "VITAMINA D3",
            "amount": "1000",
            "unit": "UI",
            "amount_mg": "",
            "component_match_score": "100",
            "price": "30.0",
            "currency": "PEN",
            "availability": "available",
            "url": "https://example.test/a",
            "sku": "a",
            "brand": "A",
            "regulatory_status": "digemid_match",
        },
        {
            "pharmacy": "Mifarma",
            "commercial_name": "Vitamina D B",
            "formal_name": "Vitamina D",
            "registro_sanitario": "DE-2",
            "digemid_producto": "VITAMINA D",
            "component_id": "cmp_vit_d",
            "ingredient": "VITAMINA D3",
            "amount": "1000",
            "unit": "UI",
            "amount_mg": "",
            "component_match_score": "100",
            "price": "32.0",
            "currency": "PEN",
            "availability": "available",
            "url": "https://example.test/b",
            "sku": "b",
            "brand": "B",
            "regulatory_status": "digemid_match",
        },
        {
            "pharmacy": "Inkafarma",
            "commercial_name": "Calcio A",
            "formal_name": "Calcio",
            "registro_sanitario": "DE-3",
            "digemid_producto": "CALCIO",
            "component_id": "cmp_calcium",
            "ingredient": "CALCIO",
            "amount": "500",
            "unit": "mg",
            "amount_mg": "500",
            "component_match_score": "100",
            "price": "20.0",
            "currency": "PEN",
            "availability": "available",
            "url": "https://example.test/c",
            "sku": "c",
            "brand": "C",
            "regulatory_status": "digemid_match",
        },
    ]

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def test_products_for_component_returns_distinct_pharmacies(tmp_path):
    catalog_path = tmp_path / "approved_catalog.csv"
    _write_catalog(catalog_path)
    _catalog_by_component.cache_clear()

    service = ProductCatalogService(catalog_path=catalog_path)
    products = service.products_for_component("cmp_vit_d", limit=2)

    assert [product["pharmacy"] for product in products] == ["Inkafarma", "Mifarma"]
    assert all(product["regulatory_status"] == "digemid_match" for product in products)


def test_pack_selection_penalizes_repeated_pharmacy_when_possible(tmp_path):
    catalog_path = tmp_path / "approved_catalog.csv"
    _write_catalog(catalog_path)
    _catalog_by_component.cache_clear()

    service = ProductCatalogService(catalog_path=catalog_path)
    selected = service.select_products_for_pack(["cmp_vit_d", "cmp_calcium"])

    assert len(selected) == 2
    assert {product["component_id"] for product in selected} == {"cmp_vit_d", "cmp_calcium"}
    assert all(product["url"].startswith("https://example.test/") for product in selected)


def test_db_pack_selection_uses_published_review_metrics(monkeypatch):
    products = [
        {
            "product_id": "11111111-1111-1111-1111-111111111111",
            "pharmacy": "Inkafarma",
            "commercial_name": "Barato con malas reviews",
            "formal_name": "Vitamina D",
            "registro_sanitario": "DE-1",
            "digemid_producto": "VITAMINA D",
            "component_id": "cmp_vit_d",
            "ingredient": "VITAMINA D3",
            "amount": "1000",
            "unit": "UI",
            "amount_mg": None,
            "component_match_score": 100,
            "price": 20.0,
            "currency": "PEN",
            "availability": "available",
            "stock": 20,
            "url": "https://example.test/bad",
            "sku": "bad",
            "brand": "A",
            "regulatory_status": "digemid_match",
            "last_seen_at": None,
        },
        {
            "product_id": "22222222-2222-2222-2222-222222222222",
            "pharmacy": "Mifarma",
            "commercial_name": "Medio con buenas reviews",
            "formal_name": "Vitamina D",
            "registro_sanitario": "DE-2",
            "digemid_producto": "VITAMINA D",
            "component_id": "cmp_vit_d",
            "ingredient": "VITAMINA D3",
            "amount": "1000",
            "unit": "UI",
            "amount_mg": None,
            "component_match_score": 100,
            "price": 35.0,
            "currency": "PEN",
            "availability": "available",
            "stock": 20,
            "url": "https://example.test/good",
            "sku": "good",
            "brand": "B",
            "regulatory_status": "digemid_match",
            "last_seen_at": None,
        },
    ]

    class FakeCatalogRepository:
        def __init__(self, _db):
            pass

        def products_for_component(self, component_id, limit=50):
            assert component_id == "cmp_vit_d"
            return products[:limit]

    class FakeReviewMetricsRepository:
        def __init__(self, _db):
            pass

        def product_metrics(self, _product_ids):
            return {
                "11111111-1111-1111-1111-111111111111": {
                    "review_score": 0.20,
                    "bayesian_review_score": 0.20,
                    "review_count": 20,
                    "avg_rating": 1.8,
                    "verified_review_count": 0,
                    "verified_review_ratio": 0.0,
                },
                "22222222-2222-2222-2222-222222222222": {
                    "review_score": 0.95,
                    "bayesian_review_score": 0.95,
                    "review_count": 40,
                    "avg_rating": 4.8,
                    "verified_review_count": 8,
                    "verified_review_ratio": 0.2,
                },
            }

    monkeypatch.setattr(product_catalog_module, "CatalogRepository", FakeCatalogRepository)
    monkeypatch.setattr(product_catalog_module, "ReviewMetricsRepository", FakeReviewMetricsRepository)

    service = ProductCatalogService(db=object())
    selected = service.select_products_for_pack(["cmp_vit_d"])

    assert selected[0]["product_id"] == "22222222-2222-2222-2222-222222222222"
    assert selected[0]["review_count"] == 40
    assert selected[0]["product_score"] > products[0].get("product_score", 0)
    assert "Reviews publicadas positivas" in selected[0]["selection_reasons"]
