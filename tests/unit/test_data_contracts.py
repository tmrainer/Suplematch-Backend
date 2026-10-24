"""Contratos de integridad de la base de conocimiento (data/knowledge).

Varios tests son "ratchets": fijan el nivel actual de deuda (duplicados, perfiles faltantes) para que
no crezca, mientras la Fase 2 del plan de fiabilidad los lleva a cero.
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE = ROOT / "data" / "knowledge"

TABLES_WITH_SOURCES = (
    "conditions.csv",
    "condition_rules.csv",
    "biomarkers.csv",
    "condition_component_links.csv",
    "component_evidence_profiles.csv",
    "component_claim_evidence.csv",
    "component_interaction_rules.csv",
    "component_life_stage_guidance.csv",
    "safety_rules.csv",
)

# Deuda conocida al 2026-10-22. Bajar, nunca subir.
KNOWN_DUPLICATE_LINK_PAIRS = 0
KNOWN_LINK_COMPONENTS_WITHOUT_PROFILE = 0


def _read(name: str) -> list[dict[str, str]]:
    with (KNOWLEDGE / name).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _split(value: str | None) -> list[str]:
    return [item for item in (value or "").split("|") if item]


def _norm(value: str | None) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch)).strip().lower()


@pytest.fixture(scope="module")
def sources() -> dict[str, dict[str, str]]:
    return {row["source_id"]: row for row in _read("sources.csv")}


@pytest.fixture(scope="module")
def condition_codes() -> set[str]:
    return {row["condition_code"] for row in _read("conditions.csv")}


@pytest.mark.parametrize("table", TABLES_WITH_SOURCES)
def test_every_source_id_resolves(table: str, sources: dict[str, dict[str, str]]) -> None:
    unresolved = []
    for row in _read(table):
        for source_id in _split(row.get("source_ids")):
            if source_id not in sources:
                unresolved.append((table, source_id))
    assert not unresolved, unresolved


def test_sources_have_https_urls_and_titles(sources: dict[str, dict[str, str]]) -> None:
    for source_id, row in sources.items():
        assert row["url"].startswith("https://"), source_id
        assert row["title"].strip(), source_id
        assert row["organization"].strip(), source_id


def test_source_ids_are_unique() -> None:
    counts = Counter(row["source_id"] for row in _read("sources.csv"))
    assert [k for k, v in counts.items() if v > 1] == []


@pytest.mark.parametrize(
    "table", ["condition_component_links.csv", "condition_rules.csv", "condition_data_requirements.csv"]
)
def test_condition_codes_exist_in_conditions_table(table: str, condition_codes: set[str]) -> None:
    unknown = {row["condition_code"] for row in _read(table)} - condition_codes
    assert not unknown, unknown


def test_every_condition_has_at_least_one_component_link(condition_codes: set[str]) -> None:
    linked = {row["condition_code"] for row in _read("condition_component_links.csv")}
    safety_only = {code for code in condition_codes if code.startswith("SAFETY_")}
    assert condition_codes - linked - safety_only == set()


def test_condition_positive_thresholds_are_sane() -> None:
    for row in _read("conditions.csv"):
        threshold = float(row["positive_threshold"])
        assert 0.3 <= threshold <= 0.95, (row["condition_code"], threshold)


def test_condition_rule_weights_are_bounded() -> None:
    for row in _read("condition_rules.csv"):
        weight = float(row["weight"])
        assert 0.0 < weight <= 0.95, row


def test_link_evidence_strength_uses_known_vocabulary() -> None:
    allowed = {"high", "moderate", "low_moderate", "low", "contextual"}
    values = {row["evidence_strength"] for row in _read("condition_component_links.csv")}
    assert values <= allowed, values - allowed


EVIDENCE_GRADES = {"high", "moderate", "low", "very_low", "expert_opinion"}


@pytest.mark.parametrize("table", ["condition_component_links.csv", "component_claim_evidence.csv"])
def test_evidence_grade_uses_canonical_vocabulary(table: str) -> None:
    values = {row["evidence_grade"] for row in _read(table)}
    assert values and values <= EVIDENCE_GRADES, values - EVIDENCE_GRADES


def test_condition_rules_declare_weight_basis() -> None:
    for row in _read("condition_rules.csv"):
        assert row["weight_basis"] in {"expert_heuristic", "calibrated_real_data"}, row
        assert row["source_ids"], row


def test_biomarkers_have_default_row_and_consistent_variants() -> None:
    rows = _read("biomarkers.csv")
    by_code: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_code.setdefault(row["biomarker_code"], []).append(row)
    for code, items in by_code.items():
        defaults = [r for r in items if r["sex"] == "any" and r["pregnant"] == "any" and not r["age_min"] and not r["age_max"]]
        assert len(defaults) == 1, (code, len(defaults))
        units = {r["unit"] for r in items}
        assert len(units) == 1, (code, units)
        for r in items:
            assert r["sex"] in {"any", "female", "male"}, r
            assert r["pregnant"] in {"any", "yes", "no"}, r
            for item in (r["alt_units"] or "").split("|"):
                if item:
                    unit, factor = item.split(":")
                    assert float(factor) > 0, (code, unit)


def test_thyroid_safety_code_is_unified() -> None:
    for table in ("biomarkers.csv", "condition_data_requirements.csv", "component_interaction_rules.csv"):
        for row in _read(table):
            assert "disfuncion_tiroidea" not in ",".join(row.values()), (table, row)


def test_duplicate_condition_component_pairs_do_not_grow() -> None:
    pairs = Counter(
        (row["condition_code"], _norm(row["component"])) for row in _read("condition_component_links.csv")
    )
    duplicates = {pair: count for pair, count in pairs.items() if count > 1}
    assert len(duplicates) <= KNOWN_DUPLICATE_LINK_PAIRS, duplicates


def test_link_components_without_evidence_profile_do_not_grow() -> None:
    profiles = {_norm(row["component"]) for row in _read("component_evidence_profiles.csv")}
    missing = {_norm(row["component"]) for row in _read("condition_component_links.csv")} - profiles
    assert len(missing) <= KNOWN_LINK_COMPONENTS_WITHOUT_PROFILE, missing


def test_biomarkers_table_has_consistent_thresholds() -> None:
    rows = _read("biomarkers.csv")
    assert rows
    for row in rows:
        values = {col: float(row[col]) for col in ("low", "borderline", "critical_low", "high", "critical_high") if row.get(col)}
        if "critical_low" in values and "low" in values:
            assert values["critical_low"] <= values["low"], row
        if "borderline" in values and "low" in values:
            assert values["low"] <= values["borderline"], row
        if "high" in values and "critical_high" in values:
            assert values["high"] <= values["critical_high"], row
        if "low" in values and "high" in values:
            assert values["low"] < values["high"], row


SURVEY_SAFETY_CODES = {
    "ninguna", "embarazo_lactancia", "enfermedad_renal", "enfermedad_hepatica", "problema_tiroideo",
    "anticoagulantes", "medicacion_cronica", "diabetes_medicada", "inmunosupresion", "sedantes", "hipertension",
}
# Codigos que el backend deriva de otras respuestas (servicio_recomendaciones._derived_safety_context).
DERIVED_SAFETY_CODES = {"insomnio"}
# Toda regla debe poder activarse: ningun trigger fuera de la encuesta o de los derivados.
KNOWN_ORPHAN_SAFETY_TRIGGERS: set[tuple[str, str]] = set()


def test_interaction_rule_safety_triggers_match_survey_codes_or_are_known_orphans() -> None:
    orphans = {
        (row["component"], row["trigger_value"])
        for row in _read("component_interaction_rules.csv")
        if row["trigger_field"] == "condiciones_seguridad"
        and row["trigger_value"] not in SURVEY_SAFETY_CODES | DERIVED_SAFETY_CODES
    }
    assert orphans <= KNOWN_ORPHAN_SAFETY_TRIGGERS, orphans - KNOWN_ORPHAN_SAFETY_TRIGGERS


def test_survey_contract_lists_every_safety_code_of_the_schema() -> None:
    from typing import get_args

    from app.domains.survey.contrato import SURVEY_ENUMS, SURVEY_RULES
    from app.domains.survey.esquemas_encuesta import CondicionSeguridad
    from app.domains.recommendations.reglas_presentacion import (
        HARD_SAFETY_CONDITIONS,
        SECURITY_WARNING_LABELS,
        TARGETED_SAFETY_CONDITIONS,
    )

    schema_codes = set(get_args(CondicionSeguridad))
    assert schema_codes == SURVEY_SAFETY_CODES
    assert set(SURVEY_ENUMS["condiciones_seguridad"]) == schema_codes
    hard = set(SURVEY_RULES["hard_safety_values"]["condiciones_seguridad"])
    targeted = set(SURVEY_RULES["targeted_safety_values"]["condiciones_seguridad"])
    assert hard == HARD_SAFETY_CONDITIONS and targeted == TARGETED_SAFETY_CONDITIONS
    assert hard | targeted == schema_codes - {"ninguna"}
    assert schema_codes - {"ninguna"} <= set(SECURITY_WARNING_LABELS)
    assert DERIVED_SAFETY_CODES <= set(SECURITY_WARNING_LABELS)


# --- component_id canónico (Fase 2: joins por id, no por nombre) -------------------------------

COMPONENT_TABLES = (
    "condition_component_links.csv",
    "component_evidence_profiles.csv",
    "component_claim_evidence.csv",
    "component_interaction_rules.csv",
    "component_life_stage_guidance.csv",
)
COMPONENT_ID_PATTERN = r"^COMP_[0-9A-F]{12}$"


def _norm_key(value: str | None) -> str:
    import re

    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", _norm(value))).strip()


@pytest.fixture(scope="module")
def component_aliases() -> dict[str, dict[str, str]]:
    rows = _read("component_aliases.csv")
    assert rows
    return {row["component_id"]: row for row in rows}


def test_component_aliases_ids_and_names_are_unique_and_well_formed() -> None:
    import re

    rows = _read("component_aliases.csv")
    ids = [row["component_id"] for row in rows]
    assert len(ids) == len(set(ids)), [k for k, v in Counter(ids).items() if v > 1]
    names = [_norm_key(row["canonical_name_es"]) for row in rows]
    assert len(names) == len(set(names)), [k for k, v in Counter(names).items() if v > 1]
    for row in rows:
        assert re.match(COMPONENT_ID_PATTERN, row["component_id"]), row
        assert row["canonical_name_es"].strip() and row["canonical_name_en"].strip(), row
        assert _split(row["aliases"]), row


def test_component_alias_keys_resolve_to_a_single_id() -> None:
    owner: dict[str, str] = {}
    conflicts = []
    for row in _read("component_aliases.csv"):
        for alias in (row["canonical_name_es"], row["canonical_name_en"], *_split(row["aliases"])):
            key = _norm_key(alias)
            if owner.setdefault(key, row["component_id"]) != row["component_id"]:
                conflicts.append((alias, owner[key], row["component_id"]))
    assert conflicts == []


@pytest.mark.parametrize("table", COMPONENT_TABLES)
def test_every_component_row_has_a_known_component_id(table: str, component_aliases: dict[str, dict[str, str]]) -> None:
    rows = _read(table)
    assert rows and "component_id" in rows[0], table
    unknown = [(row["component"], row["component_id"]) for row in rows if row["component_id"] not in component_aliases]
    assert unknown == []


@pytest.mark.parametrize("table", COMPONENT_TABLES)
def test_component_name_matches_canonical_name_of_its_id(table: str, component_aliases: dict[str, dict[str, str]]) -> None:
    mismatched = [
        (row["component_id"], row["component"], component_aliases[row["component_id"]]["canonical_name_es"])
        for row in _read(table)
        if row["component"] != component_aliases[row["component_id"]]["canonical_name_es"]
    ]
    assert mismatched == []


def test_every_link_component_id_has_an_evidence_profile() -> None:
    profiles = {row["component_id"] for row in _read("component_evidence_profiles.csv")}
    missing = {(row["component_id"], row["component"]) for row in _read("condition_component_links.csv") if row["component_id"] not in profiles}
    assert missing == set()


def test_modelo2_component_dictionaries_are_derived_from_component_aliases(component_aliases: dict[str, dict[str, str]]) -> None:
    from app.ml.runtime.modelo2_inference import (
        COMPONENT_ALIASES,
        COMPONENT_DISPLAY_BY_ID,
        COMPONENT_ID_OVERRIDES,
        _normalize_text,
    )

    expected_ids = {_normalize_text(row["canonical_name_es"]): cid for cid, row in component_aliases.items()}
    assert COMPONENT_ID_OVERRIDES == expected_ids
    assert COMPONENT_DISPLAY_BY_ID == {cid: row["canonical_name_es"] for cid, row in component_aliases.items()}
    assert set(COMPONENT_ALIASES) == set(expected_ids)
    # Ids que el catálogo (data/catalog/approved_catalog.csv) y otros tests dan por fijos.
    assert COMPONENT_ID_OVERRIDES["vitamina d"] == "COMP_94DFE28A9A5C"
    assert COMPONENT_ID_OVERRIDES["vitamina c"] == "COMP_67B16EEFC42F"
    assert COMPONENT_ID_OVERRIDES["creatina"] == "COMP_7B47CDB437E8"
    assert COMPONENT_ID_OVERRIDES["manganeso"] == "COMP_5FCBE278ABF3"
