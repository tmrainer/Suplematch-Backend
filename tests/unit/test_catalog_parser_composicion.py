from __future__ import annotations

import pandas as pd

from scripts.catalog.parser_composicion import (
    UNIT_TO_MG,
    expand_composition_to_rows,
    parse_composition,
)


def _triples(parsed: list[dict]) -> list[tuple[str, float, str]]:
    return [(item["ingredient"], item["amount"], item["unit"]) for item in parsed]


def test_digemid_thousands_with_comma_and_six_decimals_do_not_break_name_or_amount():
    # Caso real del catálogo: antes quedaba "VITAMINA D3 2" con amount=0.0
    parsed = parse_composition("VITAMINA D3 2,000.000000 UI")

    assert parsed == [
        {"ingredient": "VITAMINA D3", "amount": 2000.0, "unit": "ui", "amount_mg": None, "salt_form": None}
    ]


def test_digemid_format_never_treats_space_as_thousands_separator():
    # "D3 100" debe ser D3 + 100 UI, no 3100 UI
    parsed = parse_composition("CALCIO 300.000000 mg VITAMINA D3 100.000000 UI OXIDO DE ZINC 9.333000 mg")

    assert _triples(parsed) == [
        ("CALCIO", 300.0, "mg"),
        ("VITAMINA D3", 100.0, "ui"),
        ("OXIDO DE ZINC", 9.333, "mg"),
    ]


def test_space_thousands_separator_in_free_text():
    assert _triples(parse_composition("VITAMINA D 2 000 UI")) == [("VITAMINA D", 2000.0, "ui")]
    assert _triples(parse_composition("Vitamina D3 2 000 UI colecalciferol")) == [("VITAMINA D3", 2000.0, "ui")]
    # Nombres con dígito pegado o numerados no se absorben en el número
    assert _triples(parse_composition("VITAMINA B12 500 mcg")) == [("VITAMINA B12", 500.0, "mcg")]
    assert _triples(parse_composition("OMEGA 3 500 mg")) == [("OMEGA 3", 500.0, "mg")]


def test_probiotic_ufc_and_cfu_units_are_kept_without_mg_conversion():
    parsed = parse_composition(
        "LACTOBACILLUS BULGARICUS 1,000,000.000000 UFC LACTOBACILLUS ACIDOPHILUS 5,000,000.000000 UFC "
        "VITAMINA C 40.000000 mg"
    )

    assert parsed[0] == {
        "ingredient": "LACTOBACILLUS BULGARICUS",
        "amount": 1_000_000.0,
        "unit": "UFC",
        "amount_mg": None,
        "salt_form": None,
    }
    assert parsed[1]["ingredient"] == "LACTOBACILLUS ACIDOPHILUS"
    assert parsed[1]["amount"] == 5_000_000.0
    assert parsed[2] == {"ingredient": "VITAMINA C", "amount": 40.0, "unit": "mg", "amount_mg": 40.0, "salt_form": None}

    cfu = parse_composition("BIFIDOBACTERIUM LACTIS 5,000,000,000 CFU")
    assert cfu == [
        {"ingredient": "BIFIDOBACTERIUM LACTIS", "amount": 5e9, "unit": "UFC", "amount_mg": None, "salt_form": None}
    ]


def test_probiotic_scientific_notation():
    parsed = parse_composition("LACTOBACILLUS RHAMNOSUS 1 x 10^9 UFC")

    assert parsed[0]["amount"] == 1e9
    assert parsed[0]["unit"] == "UFC"


def test_kilograms_are_not_converted_to_absurd_mg():
    parsed = parse_composition("PROTEINA DE SUERO 1 kg")

    assert UNIT_TO_MG["kg"] is None
    assert parsed == [{"ingredient": "PROTEINA DE SUERO", "amount": 1.0, "unit": "kg", "amount_mg": None, "salt_form": None}]


def test_serving_header_is_not_an_ingredient():
    parsed = parse_composition("POR DOSIS 15.00 mL - VITAMINA A 2,500.000000 UI VITAMINA B1 5.000000 mg")

    assert _triples(parsed) == [("VITAMINA A", 2500.0, "ui"), ("VITAMINA B1", 5.0, "mg")]

    without_unit = parse_composition("POR SOBRE 11.40 - COLAGENO HIDROLIZADO BOVINO TIPO II 10.000000 g")
    assert _triples(without_unit) == [("COLAGENO HIDROLIZADO BOVINO TIPO II", 10.0, "g")]
    assert without_unit[0]["amount_mg"] == 10000.0


def test_salt_form_parentheses_are_not_separate_ingredients():
    parsed = parse_composition("ZINC (COMO SULFATO DE ZINC MONOHIDRATO) 10.000000 mg ACIDO FOLICO 0.400000 mg")

    assert parsed == [
        {
            "ingredient": "ZINC",
            "amount": 10.0,
            "unit": "mg",
            "amount_mg": 10.0,
            "salt_form": "COMO SULFATO DE ZINC MONOHIDRATO",
        },
        {"ingredient": "ACIDO FOLICO", "amount": 0.4, "unit": "mg", "amount_mg": 0.4, "salt_form": None},
    ]


def test_salt_form_with_inner_dose_after_amount_attaches_to_previous_ingredient():
    parsed = parse_composition("ZINC 10 mg (COMO SULFATO DE ZINC 27.5 mg) VITAMINA C 100 mg")

    assert _triples(parsed) == [("ZINC", 10.0, "mg"), ("VITAMINA C", 100.0, "mg")]
    assert parsed[0]["salt_form"] == "COMO SULFATO DE ZINC 27.5 MG"
    assert parsed[1]["salt_form"] is None

    trailing = parse_composition("HIERRO 60 mg (EQUIVALENTE A 180 mg DE FUMARATO FERROSO)")
    assert _triples(trailing) == [("HIERRO", 60.0, "mg")]
    assert trailing[0]["salt_form"] == "EQUIVALENTE A 180 MG DE FUMARATO FERROSO"


def test_descriptive_parentheses_stay_in_ingredient_name():
    parsed = parse_composition("VITAMINA E (TOCOFEROL) 400.000000 UI ACIDO EICOSAPENTAENOICO (EPA) 25.000000 mg")

    assert _triples(parsed) == [("VITAMINA E (TOCOFEROL)", 400.0, "ui"), ("ACIDO EICOSAPENTAENOICO (EPA)", 25.0, "mg")]
    assert all(item["salt_form"] is None for item in parsed)


def test_micrograms_variants_and_european_decimal():
    assert parse_composition("VITAMINA B12 12.000000 MCG")[0]["amount_mg"] == 0.012
    assert parse_composition("ACIDO FOLICO 400 µg")[0]["amount_mg"] == 0.4
    assert _triples(parse_composition("MAGNESIO 1.000,5 mg")) == [("MAGNESIO", 1000.5, "mg")]


def test_expand_composition_to_rows_keeps_products_without_parse():
    df = pd.DataFrame(
        [
            {"item": "DE1", "Composición": "VITAMINA D3 2,000.000000 UI"},
            {"item": "DE2", "Composición": ""},
        ]
    )

    df_long = expand_composition_to_rows(df)

    assert list(df_long.columns) == ["item", "ingredient", "amount", "unit", "amount_mg", "salt_form"]
    assert df_long.loc[df_long["item"] == "DE1", "amount"].tolist() == [2000.0]
    assert df_long.loc[df_long["item"] == "DE2", "ingredient"].isna().all()
