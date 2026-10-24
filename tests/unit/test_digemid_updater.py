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


def test_merge_rows_adds_updates_and_never_deletes() -> None:
    from scripts.digemid.actualizar_digemid import merge_rows

    existing = [
        {"item": "DE0001", "Producto": "VIEJO", "Composición": "ZINC 10 mg", "Fabricante": "Lab A"},
        {"item": "DE0002", "Producto": "SOLO EN MAESTRO", "Composición": "MAGNESIO 100 mg"},
    ]
    incoming = [
        {"item": "de-0001", "Producto": "NUEVO NOMBRE", "Composición": "", "Fabricante": "Lab A"},
        {"item": "DE0003", "Producto": "AGREGADO", "Composición": "VITAMINA C 500 mg"},
    ]

    rows, stats = merge_rows(existing, incoming)
    by_rs = {row["item"]: row for row in rows}

    assert stats == {
        "existing_rows": 2,
        "incoming_rows": 2,
        "added": 1,
        "updated": 1,
        "unchanged": 0,
        "total_rows": 3,
    }
    assert by_rs["DE0001"]["Producto"] == "NUEVO NOMBRE"
    assert by_rs["DE0001"]["Composición"] == "ZINC 10 mg", "un vacío en la fuente no borra el dato previo"
    assert "DE0002" in by_rs, "nada se elimina"
    assert by_rs["DE0003"]["Producto"] == "AGREGADO"


def test_update_from_source_merges_with_existing_master_and_keeps_backup(tmp_path) -> None:
    source = tmp_path / "digemid_source.csv"
    out = tmp_path / "digemid_limpio.csv"
    snapshots = tmp_path / "snapshots"
    components = tmp_path / "product_components.csv"
    components.write_text("item,ingredient,component_id,match_score\n", encoding="utf-8")

    out.write_text(
        "item,Producto,Composición,Fabricante\n"
        "DE0001,VIEJO,ZINC 10 mg,Lab A\n"
        "DE0002,SOLO EN MAESTRO,MAGNESIO 100 mg,Lab B\n",
        encoding="utf-8",
    )
    source.write_text(
        "registro_sanitario,producto,composicion\n"
        "DE0001,NUEVO NOMBRE,ZINC 10 mg\n"
        "DE0003,AGREGADO,VITAMINA C 500 mg\n",
        encoding="utf-8",
    )

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
    assert report["mode"] == "merge"
    assert report["merge"]["added"] == 1
    assert report["merge"]["updated"] == 1
    assert report["rows"] == 3

    with out.open(newline="", encoding="utf-8") as handle:
        rows = {row["item"]: row for row in csv.DictReader(handle)}
    assert set(rows) == {"DE0001", "DE0002", "DE0003"}
    assert rows["DE0001"]["Producto"] == "NUEVO NOMBRE"
    assert rows["DE0001"]["Fabricante"] == "Lab A"
    assert rows["DE0002"]["Producto"] == "SOLO EN MAESTRO"

    backups = list(snapshots.glob("digemid_limpio_previous_*.csv"))
    assert backups and report["backup"] == str(backups[0])
    assert "SOLO EN MAESTRO" in backups[0].read_text(encoding="utf-8")


def test_update_from_source_min_rows_applies_to_incoming_rows(tmp_path) -> None:
    source = tmp_path / "digemid_source.csv"
    out = tmp_path / "digemid_limpio.csv"
    components = tmp_path / "product_components.csv"
    components.write_text("item,ingredient,component_id,match_score\n", encoding="utf-8")
    out.write_text("item,Producto,Composición\n" + "".join(f"DE{i:04d},P{i},C{i}\n" for i in range(50)), encoding="utf-8")
    source.write_text("registro_sanitario,producto,composicion\nDE9999,UNO,ZINC\n", encoding="utf-8")

    with pytest.raises(DigemidUpdateError, match="too_few_rows:1<min_rows:10"):
        update_from_source(
            source_file=source,
            source_url=None,
            out_path=out,
            snapshot_dir=tmp_path / "snapshots",
            components_path=components,
            min_rows=10,
            timeout=5,
        )
    assert "UNO" not in out.read_text(encoding="utf-8"), "el maestro no se toca si la fuente es insuficiente"
