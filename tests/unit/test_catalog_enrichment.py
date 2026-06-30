from scripts.catalog.enriquecer_catalogo_verificable import enrich_row


def test_enrich_row_marks_softgel_from_digemid_form():
    row = {
        "commercial_name": "Omega 3",
        "digemid_forma_farmaceutica": "CAPSULA BLANDA",
        "digemid_composicion": "ACEITE DE PESCADO 1000 mg",
    }

    enriched = enrich_row(row, "2026-06-23T00:00:00+00:00")

    assert enriched["contains_fish"] == "true"
    assert enriched["contains_gelatin"] == "true"
    assert enriched["softgel_verified"] == "true"
    assert enriched["label_status"] == "verified"
    assert enriched["restriction_traceability_level"] == "verified"
    assert enriched["label_verification_source"] == "digemid_composicion+digemid_forma_farmaceutica"


def test_enrich_row_does_not_verify_plain_name_claims():
    row = {
        "commercial_name": "Magnesio sin gluten",
        "digemid_forma_farmaceutica": "TABLETA",
        "digemid_composicion": "MAGNESIO 200 mg",
    }

    enriched = enrich_row(row, "2026-06-23T00:00:00+00:00")

    assert enriched.get("gluten_free_verified", "") == ""
    assert enriched.get("gluten_free_inferred", "") == "true"
    assert enriched.get("label_status", "") == "inferred"
    assert enriched.get("label_verification_source", "") == ""


def test_enrich_row_infers_missing_amount_from_catalog_text():
    row = {
        "commercial_name": "Sunvit Vit C 1000mg Tableta",
        "ingredient": "ACIDO ASCORBICO",
        "component_id": "vitamina_c",
        "digemid_forma_farmaceutica": "TABLETA",
        "digemid_composicion": "",
        "amount": "",
        "unit": "",
        "amount_mg": "",
        "brand": "",
    }

    enriched = enrich_row(row, "2026-06-23T00:00:00+00:00")

    assert enriched["amount"] == "1000"
    assert enriched["unit"] == "mg"
    assert enriched["amount_mg"] == "1000"
    assert enriched["amount_source"] == "catalog_text_regex"
    assert enriched["brand"] == "Sunvit"
    assert enriched["brand_confidence"] == "high"
    assert enriched["commercial_confidence_level"] == "baja"
    assert float(enriched["commercial_confidence_score"]) < 0.60


def test_enrich_row_converts_vitamin_d_ui_to_mg_and_pack_units():
    row = {
        "commercial_name": "Vitamina D3 1000 UI Tubo 20 Un",
        "ingredient": "Vitamina D",
        "component_id": "vitamina_d",
        "digemid_forma_farmaceutica": "TABLETA",
        "digemid_composicion": "",
        "amount": "",
        "unit": "",
        "amount_mg": "",
    }

    enriched = enrich_row(row, "2026-06-23T00:00:00+00:00")

    assert enriched["amount"] == "1000"
    assert enriched["unit"] == "ui"
    assert enriched["amount_mg"] == "0.025"
    assert enriched["units_per_pack"] == "20"


def test_enrich_row_commercial_confidence_differentiates_name_match():
    row = {
        "commercial_name": "Producto ejemplo",
        "registro_sanitario": "DE-1",
        "registro_sanitario_source": "digemid_name_match",
        "regulatory_status": "digemid_match",
        "component_match_score": "96",
        "availability": "available",
        "price": "20.0",
        "amount": "500",
        "unit": "mg",
        "brand": "Marca",
    }

    enriched = enrich_row(row, "2026-06-23T00:00:00+00:00")

    assert enriched["commercial_confidence_level"] == "media"
    assert "RS inferido por DIGEMID/nombre" in enriched["commercial_confidence_reasons"]
