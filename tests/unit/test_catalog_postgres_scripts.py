"""Lógica pura de los scripts de importación/snapshots/diff del catálogo (sin BD)."""

from __future__ import annotations

import csv

from scripts.catalog.generar_diff_catalogo import (
    rejection_reason_column,
    rejection_reasons,
    summarize_rejects,
)
from scripts.catalog.guardar_snapshots_precios import unique_product_rows
from scripts.catalog.importar_catalogo_postgres import (
    DEACTIVATABLE_STATUSES,
    csv_product_identities,
    product_identity,
    select_products_to_deactivate,
)


def test_product_identity_matches_importer_key_rules():
    assert product_identity("Inkafarma", "066550", "https://inkafarma.pe/x") == ("inkafarma", "066550")
    # sin sku se usa la url, igual que _get_product
    assert product_identity("Mifarma", "", "https://mifarma.pe/p/1") == ("mifarma", "https://mifarma.pe/p/1")


def test_select_products_to_deactivate_only_missing_from_csv():
    rows = [
        {"pharmacy": "Inkafarma", "sku": "a", "url": "https://x/a", "component_id": "c1"},
        {"pharmacy": "Inkafarma", "sku": "a", "url": "https://x/a", "component_id": "c2"},  # misma product, otro componente
        {"pharmacy": "Mifarma", "sku": "b", "url": "https://x/b", "component_id": "c1"},
    ]
    seen = csv_product_identities(rows)
    assert seen == {("inkafarma", "a"), ("mifarma", "b")}

    existing = [
        (("inkafarma", "a"), "active"),  # sigue en el CSV
        (("inkafarma", "gone"), "active"),  # desapareció -> inactive
        (("inkafarma", "fav"), "preferred"),  # desapareció -> inactive
        (("inkafarma", "manual"), "blocked"),  # curaduría manual, no se toca
        (("inkafarma", "old"), "inactive"),  # ya inactivo
        (("mifarma", "b"), "active"),
        (("boticas-peru", "z"), "active"),  # farmacia ausente del CSV: no se toca
    ]

    assert select_products_to_deactivate(existing, seen) == [("inkafarma", "gone"), ("inkafarma", "fav")]
    assert DEACTIVATABLE_STATUSES == {"active", "preferred"}


def test_select_products_to_deactivate_with_empty_csv_does_nothing():
    assert select_products_to_deactivate([(("inkafarma", "a"), "active")], set()) == []


def test_unique_product_rows_one_snapshot_per_product():
    rows = [
        {"pharmacy": "Inkafarma", "sku": "multi", "url": "https://x/multi", "ingredient": "ZINC", "price": "18.0"},
        {"pharmacy": "Inkafarma", "sku": "multi", "url": "https://x/multi", "ingredient": "VITAMINA B12", "price": "18.0"},
        {"pharmacy": "Inkafarma", "sku": "", "url": "https://x/nosku", "ingredient": "CALCIO", "price": "20.0"},
        {"pharmacy": "Mifarma", "sku": "multi", "url": "https://y/multi", "ingredient": "ZINC", "price": "19.0"},
    ]

    unique = unique_product_rows(rows)

    assert [(row["pharmacy"], row["sku"] or row["url"]) for row in unique] == [
        ("Inkafarma", "multi"),
        ("Inkafarma", "https://x/nosku"),
        ("Mifarma", "multi"),
    ]
    assert unique[0]["ingredient"] == "ZINC"  # se conserva la primera fila


def test_rejection_reason_column_priority():
    assert rejection_reason_column(["pharmacy", "catalog_rejection_reason", "scraper_rejection_reason"]) == (
        "catalog_rejection_reason"
    )
    assert rejection_reason_column(["pharmacy", "rejection_reason"]) == "rejection_reason"
    assert rejection_reason_column(["pharmacy", "reason"]) == "reason"
    assert rejection_reason_column(["pharmacy"]) is None
    assert rejection_reasons({"pharmacy": "x"}, None) == ["unknown"]


def test_summarize_rejects_uses_catalog_rejection_reason(tmp_path):
    path = tmp_path / "approved_catalog_rejections.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["pharmacy", "scraper_rejection_reason", "catalog_rejection_reason"])
        writer.writeheader()
        writer.writerow({"pharmacy": "Inkafarma", "scraper_rejection_reason": "", "catalog_rejection_reason": "non_supplement_category"})
        writer.writerow({"pharmacy": "Inkafarma", "scraper_rejection_reason": "", "catalog_rejection_reason": "rs_inferido_fanout;name_without_digemid_overlap"})
        writer.writerow({"pharmacy": "Mifarma", "scraper_rejection_reason": "rs_no_en_digemid:DE1", "catalog_rejection_reason": ""})

    summary = summarize_rejects(path)

    assert summary["rows"] == 3
    assert summary["reason_column"] == "catalog_rejection_reason"
    assert summary["by_reason"] == {
        "non_supplement_category": 1,
        "rs_inferido_fanout": 1,
        "name_without_digemid_overlap": 1,
        "unknown": 1,
    }


def test_summarize_rejects_uses_scraper_rejection_reason(tmp_path):
    path = tmp_path / "supplements_rejected.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["pharmacy", "rejection_reason"])
        writer.writeheader()
        writer.writerow({"pharmacy": "Inkafarma", "rejection_reason": "rs_sin_component_map"})
        writer.writerow({"pharmacy": "Inkafarma", "rejection_reason": "rs_sin_component_map"})

    summary = summarize_rejects(path)

    assert summary["reason_column"] == "rejection_reason"
    assert summary["by_reason"] == {"rs_sin_component_map": 2}
    assert "unknown" not in summary["by_reason"]
