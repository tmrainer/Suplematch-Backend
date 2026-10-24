from __future__ import annotations

import pytest

from scripts.catalog.filtros_categoria import categoria_no_suplemento, es_suplemento_oral


@pytest.mark.parametrize(
    "name",
    [
        "Acondicionador Pro-Vitaminas Pantene Hidratación Extrema",
        "Shampoo Sedal Prebióticos + Biotina Frasco 340 ml",
        "Drasanvi Biotina + Aloe Vera Champú - Frasco 1000 ml",
        "Pro Vitamina A Crema 50 ml SKIN10",
        "Protector solar Isdin Fusion Water SPF 50",
        "Babylac Pro 1 HMO DHA",
        "Enjuague bucal Listerine Cool Mint",
    ],
)
def test_non_supplements_are_flagged(name: str) -> None:
    assert categoria_no_suplemento(name) != ""
    assert not es_suplemento_oral(name)


@pytest.mark.parametrize(
    "name",
    [
        "Magnesio Glicinato 250 mg 60 cápsulas",
        "Vitamina D3 2000 UI Softgels",
        "Omega 3 + Vitamina E Drasanvi Cápsula Blanda",
        "Colágeno Hidrolizado + Biotina Polvo 300 g",
        "Ensure Advance Vainilla 850 g",
        "Proteína Whey Sabor Chocolate 1 kg",
        "Biotina 10,000 mcg Tabletas",
    ],
)
def test_oral_supplements_pass(name: str) -> None:
    assert categoria_no_suplemento(name) == ""
    assert es_suplemento_oral(name)


def test_brand_match_uses_word_boundaries() -> None:
    assert categoria_no_suplemento("Dove Chocolate Protein Bar") != ""  # marca de higiene conocida
    assert categoria_no_suplemento("Axel Omega 3 1000 mg") == ""  # 'axe' no debe coincidir dentro de 'Axel'
