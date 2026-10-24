"""Candado de version: las tablas clinicas no cambian sin actualizar el manifiesto a proposito."""

from __future__ import annotations

from pathlib import Path

import pytest

manifest = pytest.importorskip("scripts.clinical.manifiesto_reglas")


def test_clinical_tables_match_approved_manifest() -> None:
    changed = manifest.changed_files()
    assert not changed, (
        "Tablas clinicas cambiadas sin aprobar: "
        + ", ".join(changed)
        + ". Cambiar reglas, umbrales o interacciones cambia el comportamiento clinico: revisa el impacto con "
        "scripts/clinical/informe_impacto_reglas.py y aprueba con scripts/clinical/manifiesto_reglas.py --approve "
        "--by ... --note ..."
    )


def test_manifest_covers_all_clinical_tables() -> None:
    approved = manifest.load_manifest()
    assert set(approved["files"]) == set(manifest.CLINICAL_FILES)
    assert approved["approved_by"] and approved["note"]


def test_line_endings_do_not_change_the_hash(tmp_path: Path) -> None:
    unix, windows = tmp_path / "a.csv", tmp_path / "b.csv"
    unix.write_bytes(b"a,b\n1,2\n")
    windows.write_bytes(b"a,b\r\n1,2\r\n")
    assert manifest.file_hash(unix) == manifest.file_hash(windows)


def test_detects_a_modified_table(tmp_path: Path) -> None:
    for rel in manifest.CLINICAL_FILES:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((manifest.ROOT / rel).read_bytes())
    assert manifest.changed_files(tmp_path) == []
    rules = tmp_path / "data/knowledge/condition_rules.csv"
    rules.write_text(rules.read_text(encoding="utf-8").replace(",0.30,", ",0.31,", 1), encoding="utf-8")
    assert manifest.changed_files(tmp_path) == ["data/knowledge/condition_rules.csv"]
