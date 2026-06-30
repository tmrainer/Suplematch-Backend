from __future__ import annotations

import csv

import pytest

from scripts.digemid.actualizar_digemid import (
    DigemidUpdateError,
    current_report,
    normalize_table,
    update_from_source,
)


def test_normalize_dataframe_accepts_common_official_column_aliases() -> None:
    records = [
        {
            "N° Registro Sanitario": " DE-123 ",
            "Nombre Producto": "Vitamina C",
            "Composición": "ACIDO ASCORBICO 500 mg",
            "Fabricante": "Laboratorio Demo",
            "Forma Farmacéutica": "TABLETA",
        }
    ]

    rows = normalize_table(list(records[0].keys()), records)

    assert rows[0]["item"] == "DE123"
    assert rows[0]["Producto"] == "Vitamina C"
    assert rows[0]["Composición"] == "ACIDO ASCORBICO 500 mg"
    assert rows[0]["Forma Farmacéutica"] == "TABLETA"


def test_normalize_dataframe_requires_registry_product_and_composition() -> None:
    with pytest.raises(DigemidUpdateError, match="missing_required_columns"):
        normalize_table(["Producto"], [{"Producto": "Vitamina C"}])


def test_update_from_source_writes_snapshot_and_reportable_csv(tmp_path) -> None:
    source = tmp_path / "digemid_source.csv"
    out = tmp_path / "digemid_limpio.csv"
    snapshots = tmp_path / "snapshots"
    components = tmp_path / "product_components.csv"

    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["registro_sanitario", "producto", "composicion"])
        writer.writeheader()
        writer.writerow(
            {
                "registro_sanitario": "DE0238",
                "producto": "CREVET",
                "composicion": "ACIDO ASCORBICO 200 mg",
            }
        )
    components.write_text("item,ingredient,component_id,match_score\nDE0238,ACIDO ASCORBICO,COMP_X,100\n", encoding="utf-8")

    report = update_from_source(
        source_file=source,
        source_url=None,
        out_path=out,
        snapshot_dir=snapshots,
        components_path=components,
        min_rows=1,
        timeout=5,
    )

    assert report["status"] == "updated"
    assert report["rows"] == 1
    assert report["component_mapped_rs"] == 1
    assert out.exists()
    assert list(snapshots.glob("digemid_limpio_*.csv"))


def test_current_report_handles_existing_csv(tmp_path) -> None:
    current = tmp_path / "digemid_limpio.csv"
    components = tmp_path / "product_components.csv"
    current.write_text("item,Producto,Composición\nDE1,Demo,ACIDO ASCORBICO 1 mg\n", encoding="utf-8")
    components.write_text("item,ingredient,component_id,match_score\n", encoding="utf-8")

    report = current_report(current, components)

    assert report["exists"] is True
    assert report["rows"] == 1
    assert report["missing_component_map_rs"] == 1
