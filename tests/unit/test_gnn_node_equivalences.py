"""Tabla de equivalencias nodo GNN -> componente canonico (Fase 2/4: ids duplicados del grafo)."""

from __future__ import annotations

import csv
import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TABLE = ROOT / "data/knowledge/gnn_node_equivalences.csv"
ALIASES = ROOT / "data/knowledge/component_aliases.csv"
MASTER = ROOT / "data/training/supplement_model/Component_Master_Clean.csv"
ID_PATTERN = re.compile(r"^COMP_[0-9A-F]{12}$")


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_table_rows_are_well_formed_and_point_to_canonical_ids() -> None:
    rows = _read(TABLE)
    assert rows
    canonical_ids = {row["component_id"] for row in _read(ALIASES)}
    gnn_ids = [row["gnn_component_id"] for row in rows]
    assert len(gnn_ids) == len(set(gnn_ids)), "un nodo del grafo solo puede mapear a un canonico"
    for row in rows:
        assert ID_PATTERN.match(row["gnn_component_id"]) and ID_PATTERN.match(row["component_id"])
        assert row["component_id"] in canonical_ids, row
        assert row["gnn_component_id"] != row["component_id"], "el canonico no se mapea a si mismo"
        assert row["gnn_component_id"] not in canonical_ids, "un id canonico no puede ser alias de otro"
        assert row["match_rule"] in {"exact", "qualified", "source_page", "salt_form"}


@pytest.mark.skipif(not MASTER.exists(), reason="Component_Master_Clean.csv no versionado")
def test_table_is_in_sync_with_generator_and_master() -> None:
    spec = importlib.util.spec_from_file_location("generar_equivalencias_gnn", ROOT / "scripts/ops/generar_equivalencias_gnn.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.build_rows() == _read(TABLE), "regenerar con scripts/ops/generar_equivalencias_gnn.py"
    master_ids = {row["component_id"] for row in _read(MASTER)}
    assert {row["gnn_component_id"] for row in _read(TABLE)} <= master_ids


def test_vitamin_d_variants_collapse_to_one_canonical_id() -> None:
    from app.ml.runtime.modelo2_inference import canonical_graph_id, gnn_node_equivalences

    gnn_node_equivalences.cache_clear()
    by_name = {row["gnn_canonical_name"]: row for row in _read(TABLE)}
    plain = by_name["Vitamin D"]
    for name in ("Vitamin D", "Vitamin D (unspecified)", "Vitamin D (ergocalciferol)", "Vitamin D (MedlinePlus Supplements)"):
        assert canonical_graph_id(by_name[name]["gnn_component_id"]) == plain["component_id"]
    assert canonical_graph_id(plain["component_id"]) == plain["component_id"]
    assert canonical_graph_id("COMP_NO_EXISTE") == "COMP_NO_EXISTE"
    assert canonical_graph_id(None) is None
