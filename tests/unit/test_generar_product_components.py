"""El generador de product_components no debe repetir los errores del CSV legado."""

from __future__ import annotations

import pytest

from scripts.catalog.generar_product_components import ComponentResolver, core_nutrient_key

MASTER = [
    {"component_id": "COMP_VITC_MASTER", "canonical_name": "Vitamin C"},
    {"component_id": "COMP_ASCORBIC", "canonical_name": "ascorbic acid"},
    {"component_id": "COMP_VITD_MASTER", "canonical_name": "Vitamin D"},
    {"component_id": "COMP_B12_MASTER", "canonical_name": "Vitamin B12"},
    {"component_id": "COMP_THIAMIN", "canonical_name": "Thiamin"},
    {"component_id": "COMP_RIBO", "canonical_name": "Riboflavin"},
    {"component_id": "COMP_IODINE", "canonical_name": "Iodine"},
    {"component_id": "COMP_POTASSIUM", "canonical_name": "Potassium"},
    {"component_id": "COMP_IRON", "canonical_name": "Iron"},
    {"component_id": "COMP_FE_GLUC", "canonical_name": "ferrous gluconate"},
    {"component_id": "COMP_CREATINE", "canonical_name": "Creatine"},
    {"component_id": "COMP_FOLATE", "canonical_name": "FolateFolacin"},
    {"component_id": "COMP_B6", "canonical_name": "Vitamin B6"},
    {"component_id": "COMP_PYRIDOXAMINE", "canonical_name": "Pyridoxamine"},
]
KNOWLEDGE = {"vitamina c": "COMP_VITC_KB", "vitamina d": "COMP_VITD_KB", "creatina": "COMP_CREATINE", "yodo": "COMP_IODINE", "hierro": "COMP_IRON", "vitamina b6": "COMP_B6"}
LEGACY_WITH_BUGS = [
    {"item": "DE1", "ingredient": "VITAMINA B1", "component_id": "COMP_B12_MASTER", "match_method": "exact_translated", "match_score": "95.2"},
    {"item": "DE2", "ingredient": "CREATINA MONOHIDRATO", "component_id": "COMP_VITC_MASTER", "match_method": "fuzzy_translated", "match_score": "91"},
]


@pytest.fixture(scope="module")
def resolver() -> ComponentResolver:
    return ComponentResolver(MASTER, LEGACY_WITH_BUGS, manual_aliases={"COMP_CREATINE": ["CREATINA", "CREATINE MONOHYDRATE"]}, knowledge_ids=KNOWLEDGE)


@pytest.mark.parametrize(
    ("ingredient", "expected"),
    [
        ("VITAMINA C", "COMP_VITC_KB"),            # id de knowledge, no el duplicado del master
        ("ACIDO ASCORBICO", "COMP_VITC_KB"),       # misma vitamina, mismo id
        ("ACIDO L-ASCORBICO", "COMP_VITC_KB"),
        ("VITAMINA D3", "COMP_VITD_KB"),
        ("COLECALCIFEROL", "COMP_VITD_KB"),
        ("VITAMINA B1", "COMP_THIAMIN"),           # el legado la mandaba a B12
        ("VITAMINA B2", "COMP_RIBO"),
        ("CIANOCOBALAMINA", "COMP_B12_MASTER"),
        ("CREATINA MONOHIDRATO", "COMP_CREATINE"), # el legado la mandaba a vitamina C
        ("MALATO DE TRICREATINA", "COMP_CREATINE"),
        ("IODURO DE POTASIO", "COMP_IODINE"),      # el nutriente es el yodo, no el potasio
        ("FUMARATO FERROSO", "COMP_IRON"),
        ("CLORHIDRATO DE PIRIDOXINA", "COMP_B6"),  # no piridoxamina
        ("ACIDO FOLICO", "COMP_FOLATE"),
    ],
)
def test_resolver_maps_to_canonical_components(resolver: ComponentResolver, ingredient: str, expected: str) -> None:
    component_id, method, score = resolver.resolve(ingredient, None)
    assert component_id == expected, (ingredient, component_id, method)
    assert score >= 90


def test_unknown_ingredient_stays_unmapped_instead_of_fuzzy(resolver: ComponentResolver) -> None:
    component_id, method, score = resolver.resolve("MALTODEXTRINA", None)
    assert component_id == "" and method == "unmapped" and score == 0.0


def test_core_nutrient_key_strips_salts() -> None:
    assert core_nutrient_key("CLORHIDRATO DE PIRIDOXINA") == "PIRIDOXINA"
    assert core_nutrient_key("CITRATO DE MAGNESIO") == "MAGNESIO"
