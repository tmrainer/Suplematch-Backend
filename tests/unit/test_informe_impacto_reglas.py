"""Informe de impacto de reglas: diff y ejecucion sin reentrenar."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

rep = pytest.importorskip("scripts.clinical.informe_impacto_reglas")

HEADER = "condition_code,field,operator,value,weight,source_ids,weight_basis\n"


def test_rule_diff_reports_added_removed_and_weight_changes() -> None:
    base = rep.parse_rules(HEADER + "A,edad,gte,50,0.20,s,e\nA,sexo,eq,F,0.10,s,e\n")
    new = rep.parse_rules(HEADER + "A,edad,gte,50,0.25,s,e\nA,bmi,gte,30,0.14,s,e\n")
    diff = rep.rule_diff(base, new)
    assert [(d["field"], d["weight"]) for d in diff["added"]] == [("bmi", 0.14)]
    assert [(d["field"], d["weight"]) for d in diff["removed"]] == [("sexo", 0.10)]
    assert [(d["field"], d["before"], d["after"]) for d in diff["weight_changed"]] == [("edad", 0.20, 0.25)]


def test_in_operator_values_are_parsed_as_lists() -> None:
    rules = rep.parse_rules(HEADER + "A,benchmark_diet_b12_status,in,low|critical_low,0.18,s,e\n")
    assert rules["A"][0]["value"] == ["low", "critical_low"]


def test_same_rules_and_mode_produce_no_changes(tmp_path: Path) -> None:
    base = tmp_path / "base.csv"
    base.write_text((rep.ROOT / rep.RULES_PATH).read_text(encoding="utf-8"), encoding="utf-8")
    assert rep.main(["--base-file", str(base), "--cases", "12", "--out-dir", str(tmp_path)]) == 0
    report = json.loads(next(tmp_path.glob("impacto_reglas_*.json")).read_text(encoding="utf-8"))
    assert report["cases_with_any_change"] == 0
    assert report["rule_diff"] == {"added": [], "removed": [], "weight_changed": []}


def test_family_mode_never_detects_more_than_sum_with_same_rules(tmp_path: Path) -> None:
    assert rep.main(["--base-aggregation", "sum", "--aggregation", "family", "--cases", "30", "--out-dir", str(tmp_path)]) == 0
    report = json.loads(next(tmp_path.glob("impacto_reglas_*.json")).read_text(encoding="utf-8"))
    assert report["after"]["mean_conditions_per_case"] <= report["before"]["mean_conditions_per_case"]
