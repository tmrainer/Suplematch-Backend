import csv

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
