from __future__ import annotations

import csv
from pathlib import Path

from scripts.catalog.parser_composicion import parse_composition
from scripts.scraping.scraper_suplementos import (
    ProductRow,
    RegistryMatcher,
    extract_image_urls,
    extract_registro,
    first_image_url,
    flattened_json_text,
)
from app.domains.catalog.servicio_catalogo_productos import ProductCatalogService
from app.domains.catalog.catalogo_csv import _catalog_by_component
from app.ml.runtime.modelo2_inference import recomendar_suplementos


ROOT = Path(__file__).resolve().parents[2]
CREATINE_ID = "COMP_7B47CDB437E8"
VITAMIN_C_ID = "COMP_67B16EEFC42F"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_parser_handles_thousands_and_decimal_separators_for_creatine() -> None:
    parsed = parse_composition(
        "MALATO DE CITRULINA 4,000.000000 mg "
        "CREATINA MONOHIDRATO 3,250.000000 mg"
    )

    assert parsed == [
        {
            "ingredient": "MALATO DE CITRULINA",
            "amount": 4000.0,
            "unit": "mg",
            "amount_mg": 4000.0,
        },
        {
            "ingredient": "CREATINA MONOHIDRATO",
            "amount": 3250.0,
            "unit": "mg",
            "amount_mg": 3250.0,
        },
    ]


def test_creatine_catalog_rows_do_not_map_to_vitamin_c() -> None:
    for relative_path in [
        "data/training/supplement_model/product_components.csv",
        "data/catalog/approved_catalog.csv",
    ]:
        rows = _read_csv(ROOT / relative_path)
        creatine_rows = [
            row
            for row in rows
            if "CREATIN" in (row.get("ingredient") or "").upper()
            and "PANCREATIN" not in (row.get("ingredient") or "").upper()
        ]

        assert creatine_rows, relative_path
        assert all(row["component_id"] == CREATINE_ID for row in creatine_rows), relative_path
        assert all(row["component_id"] != VITAMIN_C_ID for row in creatine_rows), relative_path


def test_product_catalog_returns_creatine_products_under_creatine_component() -> None:
    _catalog_by_component.cache_clear()
    products = ProductCatalogService().products_for_component(CREATINE_ID, limit=3)

    assert products
    assert all(product["component_id"] == CREATINE_ID for product in products)
    assert any("CREATIN" in product["ingredient"].upper() for product in products)


def test_model2_resolves_sports_creatine_to_creatine_component() -> None:
    result = recomendar_suplementos(
        ["RENDIMIENTO_DEPORTIVO"],
        condition_scores={"RENDIMIENTO_DEPORTIVO": 0.74},
    )

    creatine = [
        item
        for item in result["recomendaciones"]
        if item.get("component_id") == CREATINE_ID
    ]

    assert creatine
    assert creatine[0]["nombre"] == "Creatina"
    assert creatine[0]["recommendation_role"] == "supportive"


def test_scraper_manual_alias_detects_creatine_without_fuzzy_vitamin_c(tmp_path) -> None:
    digemid = tmp_path / "digemid.csv"
    components = tmp_path / "components.csv"
    master = tmp_path / "master.csv"

    digemid.write_text("item,Producto\nDE1,CREATINE\n", encoding="utf-8")
    components.write_text(
        "item,ingredient,amount,unit,amount_mg,component_id,match_score,match_method\n",
        encoding="utf-8",
    )
    master.write_text(
        "component_id,canonical_name\n"
        f"{VITAMIN_C_ID},Vitamin C (ascorbic acid)\n",
        encoding="utf-8",
    )

    matcher = RegistryMatcher(digemid, components, master)
    detected = matcher.detect_components(
        ProductRow(
            pharmacy="Farmacia",
            commercial_name="Creatina monohidratada polvo oral",
            formal_name="",
            registro_sanitario="",
            price="10.0",
            currency="PEN",
            availability="available",
            url="https://example.test/creatina",
            sku="CREA",
            brand="",
            source_strategy="test",
            scraped_at="2026-06-18T00:00:00Z",
        )
    )

    assert detected == [(CREATINE_ID, "CREATINA")]


def test_scraper_extracts_common_peruvian_rs_formats() -> None:
    assert extract_registro("R.S: I4100524E/NAABLB") == "I4100524ENAABLB"
    assert extract_registro("RS:P2802921E/NKPSFR") == "P2802921ENKPSFR"
    assert extract_registro("Registro sanitario DE-4606") == "DE4606"


def test_scraper_manual_alias_detects_sleep_and_probiotic_components(tmp_path) -> None:
    digemid = tmp_path / "digemid.csv"
    components = tmp_path / "components.csv"
    master = tmp_path / "master.csv"

    digemid.write_text("item,Producto\nDE1,PRODUCTO\n", encoding="utf-8")
    components.write_text(
        "item,ingredient,amount,unit,amount_mg,component_id,match_score,match_method\n",
        encoding="utf-8",
    )
    master.write_text("component_id,canonical_name\n", encoding="utf-8")

    matcher = RegistryMatcher(digemid, components, master)
    detected = matcher.detect_components(
        ProductRow(
            pharmacy="Farmacia",
            commercial_name="L-teanina con probióticos lactobacillus",
            formal_name="Valeriana Withania somnifera",
            registro_sanitario="",
            price="10.0",
            currency="PEN",
            availability="available",
            url="https://example.test/sleep",
            sku="SLEEP",
            brand="",
            source_strategy="test",
            scraped_at="2026-06-18T00:00:00Z",
        )
    )

    detected_ids = {component_id for component_id, _ in detected}

    assert "COMP_AE7EE271FD2C" in detected_ids
    assert "COMP_D691B9C2718F" in detected_ids
    assert "COMP_E3D7A2D1C909" in detected_ids
    assert "COMP_5030A6666E7D" in detected_ids


def test_scraper_flattens_detail_text_and_extracts_image_urls() -> None:
    detail = {
        "name": "Vitamina C",
        "description": {"html": "Registro sanitario DE-1234 composicion"},
        "images": [{"url": "/assets/vitamina-c.jpg"}, {"src": "https://example.test/label.png"}],
    }

    text = flattened_json_text(detail)
    urls = extract_image_urls(detail, "https://farmacia.test")

    assert "Registro sanitario DE-1234" in text
    assert "https://farmacia.test/assets/vitamina-c.jpg" in urls
    assert "https://example.test/label.png" in urls
    assert first_image_url(["https://farmacia.test/assets/placeholder.jpg", *urls]) == "https://farmacia.test/assets/vitamina-c.jpg"


def test_scraper_infers_rs_by_high_confidence_digemid_name_match(tmp_path) -> None:
    digemid = tmp_path / "digemid.csv"
    components = tmp_path / "components.csv"
    master = tmp_path / "master.csv"

    digemid.write_text(
        "item,Producto\n"
        "DE-777,SUNVIT VITAMINA B12 B6 FOLIC TABLETA SUBLINGUAL\n",
        encoding="utf-8",
    )
    components.write_text(
        "item,ingredient,amount,unit,amount_mg,component_id,match_score,match_method\n"
        "DE-777,VITAMINA B12,1000,mcg,1,COMP_06B36D3A8FF3,95,exact\n",
        encoding="utf-8",
    )
    master.write_text("component_id,canonical_name\n", encoding="utf-8")

    matcher = RegistryMatcher(digemid, components, master)
    row = matcher.enrich(
        ProductRow(
            pharmacy="Farmacia",
            commercial_name="Sunvit Vitamina B12 B6 Folic Tableta Sublingual",
            formal_name="",
            registro_sanitario="",
            price="10.0",
            currency="PEN",
            availability="available",
            url="https://example.test/b12",
            sku="B12",
            brand="Sunvit",
            source_strategy="test",
            scraped_at="2026-06-18T00:00:00Z",
        ),
        infer_missing_rs=True,
    )

    assert row.registro_sanitario == "DE-777"
    assert row.registro_sanitario_source == "digemid_name_match"
    assert row.component_traceable == "true_rs_component"
