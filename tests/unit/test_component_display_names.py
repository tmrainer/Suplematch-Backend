"""Los nombres de suplementos que ve el usuario deben ser reconocibles: en espanol, sin sigla sola."""

from __future__ import annotations

import csv
import re
from pathlib import Path

import pytest

from app.domains.recommendations.reglas_presentacion import _translate_component_name

ROOT = Path(__file__).resolve().parents[2]
ENGLISH = re.compile(
    r"\b(vitamin|acid|folate|boron|phosphorus|calcium|magnesium|iron|selenium|copper|potassium|sodium|choline|"
    r"theanine|riboflavin|thiamine?|niacin|biotin|oil|extract|collagen|melatonin|probiotics?)\b",
    re.IGNORECASE,
)


def _knowledge_component_names() -> set[str]:
    names: set[str] = set()
    for table in ("condition_component_links.csv", "component_claim_evidence.csv"):
        with (ROOT / "data/knowledge" / table).open(encoding="utf-8-sig", newline="") as handle:
            names |= {row["component"] for row in csv.DictReader(handle) if row.get("component")}
    return names


# Nombres crudos que llegaban al usuario el 2026-10-24 (grafo del Modelo 2 y variantes sin tilde).
SEEN_RAW = ["Boron", "Phosphorus", "Folate", "Vitamin C", "Omega 3", "Acido Folico", "DHA", "EPA", "Riboflavina",
            "Tiamina", "Niacina", "Ácido pantoténico", "Bacillus coagulans", "Bifidobacterium longum", "Calcium", "Vitamin D"]


@pytest.mark.parametrize("raw", sorted(_knowledge_component_names()) + SEEN_RAW)
def test_component_names_are_recognizable(raw: str) -> None:
    shown = _translate_component_name(raw)
    assert not ENGLISH.search(shown), (raw, shown)
    assert not re.fullmatch(r"[A-Z0-9-]{2,6}", shown), (raw, shown)  # sigla sola (DHA, EPA)


def test_folic_acid_variants_share_one_name() -> None:
    names = {_translate_component_name(n) for n in ("Folate", "Folic acid", "Acido Folico", "Ácido fólico", "Folato")}
    assert names == {"Ácido fólico (vitamina B9)"}


def test_condition_names_avoid_medical_jargon() -> None:
    from app.domains.recommendations.reglas_presentacion import CONDITION_LABELS

    jargon = re.compile(r"dislipidemia|metab[oó]lic|cardiovascular|cognitiv|[oó]sea|renal|hep[aá]tic|tiroidea|capilar|folato\b|contextual", re.IGNORECASE)
    for code, label in CONDITION_LABELS.items():
        assert not jargon.search(label), (code, label)
