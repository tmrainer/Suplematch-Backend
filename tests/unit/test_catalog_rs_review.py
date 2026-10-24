"""Cola de revisión humana de RS: lógica pura (sin BD)."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from app.domains.admin.servicio_revision_rs import (
    DEFAULT_SAMPLE_RATIO,
    INFERRED_RS_SOURCES,
    build_match_reason,
    is_valid_transition,
    normalize_rs_key,
    review_product_key,
    sample_fraction,
    select_review_items,
    summarize_items,
)

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "data/catalog/approved_catalog.csv"


def _row(pharmacy, sku, source, rs="DE1000", **extra):
    base = {
        "pharmacy": pharmacy,
        "sku": sku,
        "url": f"https://{pharmacy.lower()}.test/{sku}",
        "commercial_name": f"Producto {sku}",
        "registro_sanitario": rs,
        "registro_sanitario_key": normalize_rs_key(rs),
        "registro_sanitario_source": source,
        "digemid_producto": "VITAMINA E 400 UI",
        "digemid_composicion": "DL-ALFA ACETATO DE TOCOFEROL 400.000000 UI",
        "digemid_forma_farmaceutica": "CAPSULA BLANDA",
        "component_id": "cmp_vit_e",
    }
    base.update(extra)
    return base


def test_normalize_rs_key_matches_builder_rule():
    assert normalize_rs_key("DE-1230") == "DE1230"
    assert normalize_rs_key(" de 1230 ") == "DE1230"
    assert normalize_rs_key(None) == ""


def test_review_product_key_uses_sku_or_url():
    assert review_product_key("Inkafarma", "066550", "https://x") == ("Inkafarma", "066550")
    assert review_product_key("Inkafarma", "", "https://x/p") == ("Inkafarma", "https://x/p")


def test_inferred_sources_are_the_two_name_based_ones():
    assert INFERRED_RS_SOURCES == {"digemid_name_match", "digemid_name_inference"}


def test_select_review_items_one_entry_per_product_and_all_inferred():
    rows = [
        _row("Inkafarma", "a", "digemid_name_match"),
        _row("Inkafarma", "a", "digemid_name_match", component_id="cmp_zinc"),  # misma product, otro componente
        _row("Mifarma", "b", "digemid_name_inference"),
        _row("Mifarma", "c", "vtex_spec_or_regex"),
        _row("Mifarma", "d", "page_or_detail_regex", rs=""),  # sin RS: nada que revisar
    ]
    items = select_review_items(rows, sample_ratio=0.0)
    assert [(item["pharmacy"], item["sku"]) for item in items] == [("Inkafarma", "a"), ("Mifarma", "b")]
    assert {item["sample_reason"] for item in items} == {"inferred"}
    first = items[0]
    assert first["registro_sanitario_key"] == "DE1000"
    assert first["commercial_name"] == "Producto a"
    assert first["digemid_producto"] == "VITAMINA E 400 UI"
    assert first["digemid_composicion"].startswith("DL-ALFA")
    assert first["registro_sanitario_source"] == "digemid_name_match"
    assert "forma_digemid=CAPSULA BLANDA" in first["match_reason"]


def test_select_review_items_product_is_inferred_if_any_row_is_inferred():
    rows = [
        _row("Inkafarma", "mix", "vtex_spec_or_regex"),
        _row("Inkafarma", "mix", "digemid_name_match", component_id="cmp_zinc"),
    ]
    items = select_review_items(rows, sample_ratio=0.0)
    assert len(items) == 1
    assert items[0]["sample_reason"] == "inferred"
    assert items[0]["registro_sanitario_source"] == "digemid_name_match"


def test_random_sample_is_deterministic_and_close_to_ratio():
    rows = [_row("Farmacia", f"sku-{i:05d}", "vtex_spec_or_regex") for i in range(2000)]
    first = select_review_items(rows, sample_ratio=0.05, seed="seed-a")
    second = select_review_items(rows, sample_ratio=0.05, seed="seed-a")
    assert first == second
    assert {item["sample_reason"] for item in first} == {"random_sample"}
    # ~5% con tolerancia amplia (hash uniforme sobre 2000 productos)
    assert 60 <= len(first) <= 140, len(first)

    other_seed = select_review_items(rows, sample_ratio=0.05, seed="seed-b")
    assert {i["sku"] for i in other_seed} != {i["sku"] for i in first}

    none_sampled = select_review_items(rows, sample_ratio=0.0, seed="seed-a")
    assert none_sampled == []


def test_random_sample_is_stable_when_catalog_grows():
    """Añadir productos no saca de la muestra a los ya muestreados (la cola persiste)."""
    rows = [_row("Farmacia", f"sku-{i:05d}", "vtex_spec_or_regex") for i in range(500)]
    before = {item["sku"] for item in select_review_items(rows, sample_ratio=0.1, seed="s")}
    rows += [_row("Farmacia", f"new-{i:05d}", "vtex_spec_or_regex") for i in range(200)]
    after = {item["sku"] for item in select_review_items(rows, sample_ratio=0.1, seed="s")}
    assert before <= after


def test_sample_fraction_in_unit_interval():
    value = sample_fraction(("Inkafarma", "x"), "seed")
    assert 0.0 <= value < 1.0
    assert value == sample_fraction(("Inkafarma", "x"), "seed")


def test_select_review_items_rejects_bad_ratio():
    with pytest.raises(ValueError):
        select_review_items([], sample_ratio=1.5)


def test_build_match_reason_collects_context():
    reason = build_match_reason(
        {
            "registro_sanitario_source": "digemid_name_match",
            "digemid_forma_farmaceutica": "TABLETA",
            "brand": "Marca X",
            "commercial_confidence_level": "alta",
            "commercial_confidence_reasons": "RS inferido por DIGEMID/nombre;Precio válido",
        }
    )
    assert reason.startswith("source=digemid_name_match")
    assert "forma_digemid=TABLETA" in reason
    assert "marca=Marca X" in reason
    assert "confianza_comercial=alta" in reason
    assert build_match_reason({}) == ""


def test_summarize_items_counts_by_sample_reason():
    items = [{"sample_reason": "inferred"}, {"sample_reason": "inferred"}, {"sample_reason": "random_sample"}]
    assert summarize_items(items) == {"inferred": 2, "random_sample": 1}
    assert summarize_items([]) == {"inferred": 0, "random_sample": 0}


def test_transitions_allow_known_statuses_only():
    assert is_valid_transition("pending", "approved")
    assert is_valid_transition("rejected", "pending")
    assert not is_valid_transition("pending", "deleted")
    assert not is_valid_transition("weird", "approved")


@pytest.mark.skipif(not CATALOG_PATH.exists(), reason="approved_catalog.csv no disponible")
def test_real_catalog_queue_covers_every_inferred_product():
    with CATALOG_PATH.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    inferred_products = {
        review_product_key(r.get("pharmacy"), r.get("sku"), r.get("url"))
        for r in rows
        if str(r.get("registro_sanitario_source") or "").lower() in INFERRED_RS_SOURCES
    }
    items = select_review_items(rows, sample_ratio=DEFAULT_SAMPLE_RATIO)
    queued_inferred = {(i["pharmacy"], i["sku"]) for i in items if i["sample_reason"] == "inferred"}
    assert queued_inferred == inferred_products
    # una entrada por producto
    keys = [(i["pharmacy"], i["sku"]) for i in items]
    assert len(keys) == len(set(keys))
    assert all(i["registro_sanitario_key"] for i in items)
