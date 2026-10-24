"""Agregacion de reglas por familia de evidencia y confirmacion cruzada (2026-10-24)."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from app.ml.features_contract import (
    PROXY_COMPONENTS,
    RULE_FAMILIES,
    aggregate_rule_score,
    is_corroborated,
    rule_family,
)

ROOT = Path(__file__).resolve().parents[2]


def _rule(field: str, weight: float) -> dict:
    return {"field": field, "weight": weight}


def test_same_family_counts_once_with_its_max() -> None:
    # Vitamina C: tres reglas sobre "frutas y verduras" + enfermedad frecuente.
    matched = [
        _rule("fruit_veg_servings_day", 0.22),
        _rule("vitamin_c_diet_signal", 0.20),
        _rule("benchmark_diet_vitamin_c_status", 0.42),
        _rule("enfermedad_frecuente", 0.16),
    ]
    score, families = aggregate_rule_score(matched, "family")
    # vitamin_c_diet_signal es un proxy de frutas/verduras: no suma porque esa familia ya conto.
    assert families == {"fruit_veg": 0.42, "illness": 0.16}
    assert score == pytest.approx(0.58)
    legacy, _ = aggregate_rule_score(matched, "sum")
    assert legacy == pytest.approx(1.00)


def test_rules_on_the_same_field_still_stack() -> None:
    # Escalon disenado: iron_loss_risk >= 1 (0.20) y >= 2 (0.15).
    score, families = aggregate_rule_score([_rule("iron_loss_risk", 0.20), _rule("iron_loss_risk", 0.15)], "family")
    assert families == {"iron_loss": pytest.approx(0.35)}
    assert score == pytest.approx(0.35)


def test_general_diet_flag_is_only_a_fallback() -> None:
    with_specific, families = aggregate_rule_score([_rule("dieta_deficiente", 0.28), _rule("fruit_veg_servings_day", 0.22)], "family")
    assert "diet_general" not in families and with_specific == pytest.approx(0.22)
    alone, families = aggregate_rule_score([_rule("dieta_deficiente", 0.28), _rule("fatiga_general", 0.24)], "family")
    assert families == {"proxy:dieta_deficiente": 0.28, "fatigue": 0.24}
    assert alone == pytest.approx(0.52)


def test_single_family_is_not_corroborated_without_labs() -> None:
    # Dormir poco activa meta_cognitivo, problemas_sueno y cognitive_context_signal: un solo hecho.
    _, families = aggregate_rule_score(
        [_rule("meta_cognitivo", 0.18), _rule("problemas_sueno", 0.18), _rule("cognitive_context_signal", 0.24)], "family"
    )
    assert families == {"sleep": 0.18}
    assert is_corroborated(families, "family") is False
    assert is_corroborated(families, "sum") is True
    assert is_corroborated({"lab_vitamin_d_status": 0.6}, "family") is True
    assert is_corroborated({"sun": 0.3, "age": 0.12}, "family") is True


def test_labs_are_their_own_family() -> None:
    assert rule_family("lab_ferritin_status") == "lab_ferritin_status"
    assert rule_family("benchmark_lab_vitamin_c_status") == "benchmark_lab_vitamin_c_status"


def test_every_rule_field_has_a_declared_family() -> None:
    """Un campo nuevo en condition_rules.csv debe declarar su familia en RULE_FAMILIES (o ser laboratorio);
    si no, contaria como familia propia y podria duplicar un hecho ya contado."""
    with (ROOT / "data/knowledge/condition_rules.csv").open(encoding="utf-8") as handle:
        fields = {row["field"] for row in csv.DictReader(handle)}
    declared = set(RULE_FAMILIES) | set(PROXY_COMPONENTS)
    undeclared = sorted(f for f in fields if not f.startswith(("lab_", "benchmark_lab_")) and f not in declared)
    assert undeclared == []


def test_sleep_and_stress_are_independent_evidence() -> None:
    # "Estres y sueño" se define justamente por dos hechos distintos: deben contar como dos familias.
    score, families = aggregate_rule_score([_rule("problemas_sueno", 0.30), _rule("irritabilidad", 0.28), _rule("meta_cognitivo", 0.12)], "family")
    assert families == {"sleep": 0.30, "stress": 0.28}
    assert is_corroborated(families, "family") is True


def test_overlapping_proxies_count_once() -> None:
    # Sin el dato crudo de sueño en la condicion, meta_cognitivo y cognitive_context_signal se solapan: cuenta el mayor.
    _, families = aggregate_rule_score([_rule("meta_cognitivo", 0.22), _rule("cognitive_context_signal", 0.24)], "family")
    assert families == {"proxy:cognitive_context_signal": 0.24}


def test_unknown_mode_fails_loudly() -> None:
    with pytest.raises(ValueError):
        aggregate_rule_score([], "max")
