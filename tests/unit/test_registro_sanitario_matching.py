"""Regresion del matching de registro sanitario (RS) contra DIGEMID.

Bugs cubiertos (ver docs/plan_fiabilidad.md, Fase 1):
- REGISTRO_RE aceptaba palabras comunes ("para", "Nutricion") como codigo RS.
- infer_rs usaba substring sin limites de palabra: el RS de "PRO" se asignaba a Pantene Pro-V.
"""

from __future__ import annotations

import pytest

from scripts.scraping.scraper_suplementos import (
    NAME_MATCH_THRESHOLD,
    ProductRow,
    RegistryMatcher,
    extract_registro,
    name_tokens,
    normalize_name,
    score_name_match,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Suplemento para adultos. Registro Sanitario: DE3502", "DE3502"),
        ("R.S. N° DE-04606", "DE04606"),
        ("Reg. San. EE-00123 Lote 5", "EE00123"),
        ("Omega 3 DE1000 cápsulas", "DE1000"),
        ("RS: N-12345", "N12345"),
        ("R.S: I4100524E/NAABLB", "I4100524ENAABLB"),
        ("RS:P2802921E/NKPSFR", "P2802921ENKPSFR"),
        ("Registro sanitario DE-4606", "DE4606"),
    ],
)
def test_extract_registro_accepts_real_codes(text: str, expected: str) -> None:
    assert extract_registro(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Nutricion completa",
        "Producto para el cabello",
        "Suplemento para adultos",
        "VITAMINA C DE 500 MG",
        "de 3502 unidades",
        "Energia y vitalidad",
        "",
    ],
)
def test_extract_registro_rejects_common_words_and_doses(text: str) -> None:
    assert extract_registro(text) == ""


def _score(commercial: str, digemid: str) -> float:
    query = normalize_name(commercial)
    return score_name_match(query, name_tokens(query), digemid)


def test_single_token_digemid_name_only_matches_identical_commercial_name() -> None:
    assert _score("Magnesio", "MAGNESIO .") == 1.0
    assert _score("Acondicionador Pro-Vitaminas Pantene Hidratación Extrema", "PRO .") == 0.0
    assert _score("Magnesio Glicinato 250 mg", "MAGNESIO .") == 0.0
    assert _score("Shampoo Sedal Prebióticos + Biotina", "BIOTINA .") == 0.0


def test_multi_token_digemid_name_matches_as_whole_phrase() -> None:
    assert _score("Supradyn Energy Extra 30 Tabletas", "SUPRADYN ENERGY EXTRA") == 1.0
    assert _score("Supradyn Energy", "SUPRADYN ENERGY EXTRA") == 1.0
    assert _score("Energy Drink Extra Power", "SUPRADYN ENERGY EXTRA") < NAME_MATCH_THRESHOLD


def test_match_requires_two_shared_tokens() -> None:
    assert _score("Colageno Hidrolizado Sabor Fresa", "COLAGENO MARINO PREMIUM") == 0.0


def _matcher(names: dict[str, str]) -> RegistryMatcher:
    matcher = RegistryMatcher.__new__(RegistryMatcher)
    matcher.names = [(rs, normalize_name(name)) for rs, name in names.items()]
    matcher.name_token_index = {}
    for idx, (_rs, digemid_name) in enumerate(matcher.names):
        for token in name_tokens(digemid_name):
            matcher.name_token_index.setdefault(token, set()).add(idx)
    matcher.digemid_by_rs = {rs: {"item": rs} for rs in names}
    return matcher


def _row(name: str, brand: str = "") -> ProductRow:
    return ProductRow(
        pharmacy="test",
        commercial_name=name,
        formal_name="",
        registro_sanitario="",
        price="10.00",
        currency="PEN",
        availability="available",
        url="",
        sku="sku",
        brand=brand,
        source_strategy="test",
        scraped_at="2026-01-01T00:00:00Z",
    )


def test_infer_rs_does_not_assign_generic_digemid_names_to_cosmetics() -> None:
    matcher = _matcher({"DE3502": "PRO .", "DE4606": "MAGNESIO .", "DE3564": "BIOTINA ."})

    assert matcher.infer_rs(_row("Acondicionador Pro-Vitaminas Pantene Hidratación Extrema")) == ""
    assert matcher.infer_rs(_row("Magnesio Glicinato 250 mg")) == ""
    assert matcher.infer_rs(_row("Acondicionador Sedal Prebióticos + Biotina")) == ""


def test_infer_rs_still_resolves_specific_product_names() -> None:
    matcher = _matcher({"DE1111": "SUPRADYN ENERGY EXTRA", "DE2222": "ENSURE ADVANCE VAINILLA"})

    assert matcher.infer_rs(_row("Supradyn Energy Extra 30 Tabletas")) == "DE1111"
    assert matcher.infer_rs(_row("Ensure Advance Vainilla 850 g")) == "DE2222"
    assert matcher.infer_rs(_row("Ensure Clinical Fresa")) == ""
