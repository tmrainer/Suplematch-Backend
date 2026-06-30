import csv

import app.domains.catalog.servicio_catalogo_productos as product_catalog_module
from app.domains.catalog.servicio_catalogo_productos import ProductCatalogService, _catalog_by_component


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
            "image_url": "https://img.test/vitamina-d-a.webp",
            "image_source": "card",
            "image_local_path": "data/raw/pharmacies/product_images/vitamina-d-a.webp",
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
            "image_url": "",
            "image_source": "",
            "image_local_path": "",
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
            "image_url": "",
            "image_source": "",
            "image_local_path": "",
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
    assert products[0]["image_url"] == "https://img.test/vitamina-d-a.webp"


def test_pack_selection_penalizes_repeated_pharmacy_when_possible(tmp_path):
    catalog_path = tmp_path / "approved_catalog.csv"
    _write_catalog(catalog_path)
    _catalog_by_component.cache_clear()

    service = ProductCatalogService(catalog_path=catalog_path)
    selected = service.select_products_for_pack(["cmp_vit_d", "cmp_calcium"])

    assert len(selected) == 2
    assert {product["component_id"] for product in selected} == {"cmp_vit_d", "cmp_calcium"}
    assert all(product["url"].startswith("https://example.test/") for product in selected)


def test_restrictions_penalize_marine_omega_products(tmp_path):
    catalog_path = tmp_path / "approved_catalog.csv"
    rows = [
        {
            "pharmacy": "Inkafarma",
            "commercial_name": "Omega 3 Aceite de Pescado",
            "formal_name": "Omega 3 marino",
            "registro_sanitario": "DE-OMEGA-1",
            "digemid_producto": "OMEGA 3 ACEITE DE PESCADO",
            "component_id": "cmp_omega",
            "ingredient": "EPA DHA aceite de pescado",
            "amount": "1000",
            "unit": "mg",
            "amount_mg": "1000",
            "component_match_score": "100",
            "price": "18.0",
            "currency": "PEN",
            "availability": "available",
            "url": "https://example.test/fish",
            "sku": "fish",
            "brand": "A",
            "regulatory_status": "digemid_match",
        },
        {
            "pharmacy": "Mifarma",
            "commercial_name": "Omega vegetal algas",
            "formal_name": "Omega 3 de algas",
            "registro_sanitario": "DE-OMEGA-2",
            "digemid_producto": "OMEGA 3 ALGAS",
            "component_id": "cmp_omega",
            "ingredient": "DHA de algas",
            "amount": "500",
            "unit": "mg",
            "amount_mg": "500",
            "component_match_score": "95",
            "price": "45.0",
            "currency": "PEN",
            "availability": "available",
            "url": "https://example.test/algae",
            "sku": "algae",
            "brand": "B",
            "regulatory_status": "digemid_match",
        },
    ]
    with catalog_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    _catalog_by_component.cache_clear()

    service = ProductCatalogService(
        catalog_path=catalog_path,
        restrictions=["alergia_pescado_mariscos"],
    )
    products = service.products_for_component("cmp_omega", limit=2)

    assert [product["commercial_name"] for product in products] == ["Omega vegetal algas"]
    assert all(product["sku"] != "fish" for product in products)


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
    assert "Mejor calificación de usuarios para este producto" in selected[0]["selection_reasons"]


def test_commercial_ranker_prefers_unit_product_for_specific_component(tmp_path):
    catalog_path = tmp_path / "approved_catalog.csv"
    rows = [
        {
            "pharmacy": "Inkafarma",
            "commercial_name": "B12 Complejo Multivitaminico",
            "formal_name": "Complejo B",
            "registro_sanitario": "DE-B12-MULTI",
            "digemid_producto": "COMPLEJO B",
            "component_id": "cmp_b12",
            "ingredient": "VITAMINA B12",
            "amount": "1000",
            "unit": "mcg",
            "amount_mg": "",
            "component_match_score": "100",
            "price": "18.0",
            "currency": "PEN",
            "availability": "available",
            "url": "https://example.test/multi",
            "sku": "multi",
            "brand": "A",
            "regulatory_status": "digemid_match",
        },
        {
            "pharmacy": "Inkafarma",
            "commercial_name": "B12 Complejo Multivitaminico",
            "formal_name": "Complejo B",
            "registro_sanitario": "DE-B12-MULTI",
            "digemid_producto": "COMPLEJO B",
            "component_id": "cmp_zinc",
            "ingredient": "ZINC",
            "amount": "15",
            "unit": "mg",
            "amount_mg": "15",
            "component_match_score": "90",
            "price": "18.0",
            "currency": "PEN",
            "availability": "available",
            "url": "https://example.test/multi",
            "sku": "multi",
            "brand": "A",
            "regulatory_status": "digemid_match",
        },
        {
            "pharmacy": "Mifarma",
            "commercial_name": "Vitamina B12 Unitaria",
            "formal_name": "Vitamina B12",
            "registro_sanitario": "DE-B12-UNIT",
            "digemid_producto": "VITAMINA B12",
            "component_id": "cmp_b12",
            "ingredient": "VITAMINA B12",
            "amount": "1000",
            "unit": "mcg",
            "amount_mg": "",
            "component_match_score": "100",
            "price": "26.0",
            "currency": "PEN",
            "availability": "available",
            "url": "https://example.test/unit",
            "sku": "unit",
            "brand": "B",
            "regulatory_status": "digemid_match",
        },
    ]
    with catalog_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    _catalog_by_component.cache_clear()

    service = ProductCatalogService(catalog_path=catalog_path)
    products = service.products_for_component("cmp_b12", limit=2)

    assert products[0]["commercial_name"] == "Vitamina B12 Unitaria"
    assert products[0]["component_match_type"] == "unit_component"
    assert products[1]["component_match_type"] == "multi_component"
    assert "Producto unitario priorizado para el componente" in products[0]["selection_reasons"]
    assert products[0]["commercial_score"] == products[0]["product_score"]
    assert products[0]["commercial_score_version"] == "commercial_ranker_v3_product_reviews"
    assert "unit_product_preference" in products[0]["commercial_score_breakdown"]


def test_commercial_ranker_uses_budget_when_available(tmp_path):
    catalog_path = tmp_path / "approved_catalog.csv"
    rows = [
        {
            "pharmacy": "Inkafarma",
            "commercial_name": "Vitamina D Economica",
            "formal_name": "Vitamina D",
            "registro_sanitario": "DE-D-CHEAP",
            "digemid_producto": "VITAMINA D",
            "component_id": "cmp_vit_d",
            "ingredient": "VITAMINA D3",
            "amount": "1000",
            "unit": "UI",
            "amount_mg": "",
            "component_match_score": "96",
            "price": "18.0",
            "currency": "PEN",
            "availability": "available",
            "url": "https://example.test/cheap",
            "sku": "cheap",
            "brand": "A",
            "regulatory_status": "digemid_match",
        },
        {
            "pharmacy": "Mifarma",
            "commercial_name": "Vitamina D Premium",
            "formal_name": "Vitamina D",
            "registro_sanitario": "DE-D-PREMIUM",
            "digemid_producto": "VITAMINA D",
            "component_id": "cmp_vit_d",
            "ingredient": "VITAMINA D3",
            "amount": "1000",
            "unit": "UI",
            "amount_mg": "",
            "component_match_score": "100",
            "price": "80.0",
            "currency": "PEN",
            "availability": "available",
            "url": "https://example.test/premium",
            "sku": "premium",
            "brand": "B",
            "regulatory_status": "digemid_match",
        },
    ]
    with catalog_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    _catalog_by_component.cache_clear()

    service = ProductCatalogService(catalog_path=catalog_path, budget_max=25)
    products = service.products_for_component("cmp_vit_d", limit=2)

    assert products[0]["commercial_name"] == "Vitamina D Economica"
    assert products[0]["price_score"] > products[1]["price_score"]
    assert "Elegido por mejor precio" in products[0]["selection_reasons"]
    assert products[0]["commercial_quality_flags"]["has_valid_registration"] is True
    assert products[0]["commercial_quality_flags"]["is_unit_component"] is True
