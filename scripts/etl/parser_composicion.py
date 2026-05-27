"""
parser_composicion.py
=====================
Parser de la columna `Composición` del catálogo DIGEMID.

Convierte texto como:
    "ACIDO ASCORBICO 200.000000 mg ASCORBATO DE SODIO 337.440000 mg"

en una lista estructurada:
    [
        {'ingredient': 'ACIDO ASCORBICO', 'amount': 200.0, 'unit': 'mg', 'amount_mg': 200.0},
        {'ingredient': 'ASCORBATO DE SODIO', 'amount': 337.44, 'unit': 'mg', 'amount_mg': 337.44},
    ]

Uso típico:
    df_long = expand_composition_to_rows(df_digemid, id_col='item', text_col='Composición')

Autor: [Tu nombre]
"""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Configuración de unidades reconocidas
# ---------------------------------------------------------------------------

# Unidades aceptadas y su equivalente en mg (cuando aplica)
UNIT_TO_MG: dict[str, Optional[float]] = {
    "mg": 1.0,
    "g": 1000.0,
    "kg": 1_000_000.0,
    "mcg": 0.001,
    "µg": 0.001,
    "ug": 0.001,
    # Las siguientes no son convertibles a mg directamente; se dejan como None
    "ui": None,
    "iu": None,
    "ml": None,
    "%": None,
}

UNITS_REGEX = r"(?:mg|kg|g|mcg|µg|ug|UI|IU|ml|%)"

# Patrón principal: número (con decimales o coma) seguido de una unidad reconocida.
# El nombre del ingrediente es lo que viene ANTES de cada (número + unidad).
_DOSE_PATTERN = re.compile(
    rf"(\d+(?:[\.,]\d+)?)\s*({UNITS_REGEX})\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Funciones principales
# ---------------------------------------------------------------------------

def parse_composition(text: str) -> list[dict]:
    """
    Parsea un string de composición farmacéutica de DIGEMID.

    Estrategia:
      1. Encontrar todas las posiciones donde aparece (NÚMERO + UNIDAD).
      2. El nombre del ingrediente es el texto entre el final del match anterior
         y el inicio del match actual.
      3. Esto permite que los nombres incluyan dígitos (ej. "VITAMINA B12") sin
         confundirse con la dosis.

    Parameters
    ----------
    text : str
        Texto crudo de la columna `Composición`.

    Returns
    -------
    list of dict
        Cada elemento tiene las keys: 'ingredient', 'amount', 'unit', 'amount_mg'.
        'amount_mg' es None si la unidad no es convertible a mg.
    """
    if not isinstance(text, str) or not text.strip():
        return []

    matches = list(_DOSE_PATTERN.finditer(text))
    if not matches:
        return []

    results = []
    last_end = 0

    for m in matches:
        raw_name = text[last_end:m.start()].strip()
        # Limpieza ligera del nombre
        name = _clean_ingredient_name(raw_name)

        if name:  # ignoramos si el nombre quedó vacío (p.ej. inicio del string)
            amount = float(m.group(1).replace(",", "."))
            unit = m.group(2).lower()
            mg_factor = UNIT_TO_MG.get(unit)
            amount_mg = amount * mg_factor if mg_factor is not None else None

            results.append({
                "ingredient": name,
                "amount": amount,
                "unit": unit,
                "amount_mg": amount_mg,
            })

        last_end = m.end()

    return results


def _clean_ingredient_name(name: str) -> str:
    """Limpieza básica del nombre de ingrediente parseado."""
    # Eliminar signos de puntuación al inicio o final
    name = name.strip(" ,.;:-")
    # Colapsar espacios múltiples
    name = re.sub(r"\s+", " ", name)
    # Mantener en mayúsculas (consistente con DIGEMID)
    return name.upper()


def expand_composition_to_rows(
    df: pd.DataFrame,
    id_col: str = "item",
    text_col: str = "Composición",
) -> pd.DataFrame:
    """
    Aplica el parser a un DataFrame entero y devuelve formato 'long':
    una fila por (producto, ingrediente).

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame con la tabla DIGEMID.
    id_col : str
        Nombre de la columna identificadora del producto (default 'item').
    text_col : str
        Nombre de la columna de composición (default 'Composición').

    Returns
    -------
    pd.DataFrame
        Columnas: [id_col, ingredient, amount, unit, amount_mg]
    """
    rows = []
    for _, record in df.iterrows():
        product_id = record[id_col]
        text = record[text_col]
        parsed = parse_composition(text)

        if not parsed:
            # Mantener un registro de productos sin parser exitoso
            rows.append({
                id_col: product_id,
                "ingredient": None,
                "amount": None,
                "unit": None,
                "amount_mg": None,
            })
        else:
            for ing in parsed:
                rows.append({id_col: product_id, **ing})

    return pd.DataFrame(rows)


def parser_quality_report(
    df_original: pd.DataFrame,
    df_parsed: pd.DataFrame,
    id_col: str = "item",
) -> dict:
    """
    Genera un mini-reporte de calidad del parser.

    Returns
    -------
    dict con métricas clave:
        - total_products
        - products_with_at_least_one_ingredient
        - coverage_rate
        - total_ingredients_extracted
        - unique_ingredients
    """
    total = df_original[id_col].nunique()
    df_with_ing = df_parsed.dropna(subset=["ingredient"])
    products_ok = df_with_ing[id_col].nunique()
    total_ing = len(df_with_ing)
    unique_ing = df_with_ing["ingredient"].nunique()

    return {
        "total_products": total,
        "products_with_at_least_one_ingredient": products_ok,
        "coverage_rate": round(products_ok / total, 4) if total else 0,
        "total_ingredients_extracted": total_ing,
        "unique_ingredients": unique_ing,
    }


# ---------------------------------------------------------------------------
# Demo / Tests con los ejemplos visibles del dataset
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_cases = [
        # (input, expected_count)
        ("ACIDO ASCORBICO 200.000000 mg ASCORBATO DE SODIO 337.440000 mg", 2),
        ("ACIDO FOLICO 1.000000 mg NICOTINAMIDA 8.190000 mg ZINC 0.200000 mg "
         "ACIDO EICOSAPENTAENOICO (EPA) 25.000000 mg", 4),
        ("ACIDO ASCORBICO 500.000000 mg CALCIO 100.000000 mg "
         "CIANOCOBALAMINA 0.010000 mg MAGNESIO 100.000000 mg", 4),
        ("ASPARTATO DE ARGININA 5.000000 g", 1),
        ("ACIDO FOLICO 0.800000 mg FOSFATO MONO POTASICO-PIROFOSFATO FERRICO-FOSFATO "
         "TRI CALCICO 125.000000 mg MAGNESIO 50.0 mg", 3),
        ("NICOTINAMIDA 50.000000 mg CLORHIDRATO DE PIRIDOXINA 50.000000 mg "
         "RIBOFLAVINA 5.000000 mg MONONITRATO DE TIAMINA 25.000000 mg", 4),
        # Edge case: nombre con dígito
        ("VITAMINA B12 0.001 mg ACIDO FOLICO 0.4 mg", 2),
        # Edge case: vacío
        ("", 0),
        # Edge case: gramos
        ("PARACETAMOL 500 mg CAFEINA 65 mg", 2),
    ]

    print("=" * 70)
    print("TESTS DEL PARSER")
    print("=" * 70)

    for text, expected in test_cases:
        result = parse_composition(text)
        status = "✓" if len(result) == expected else "✗"
        print(f"\n{status} Input: {text[:60]}{'...' if len(text) > 60 else ''}")
        print(f"  Esperado: {expected} ingredientes | Obtenido: {len(result)}")
        for ing in result:
            mg = f"{ing['amount_mg']} mg" if ing['amount_mg'] else "no convertible"
            print(f"    - {ing['ingredient']}: {ing['amount']} {ing['unit']}  →  {mg}")

    # Demo con un mini-DataFrame
    print("\n" + "=" * 70)
    print("DEMO: aplicación a un DataFrame pequeño")
    print("=" * 70)

    df_demo = pd.DataFrame([
        {"item": "DE0238", "Composición": "ACIDO ASCORBICO 200.000000 mg ASCORBATO DE SODIO 337.440000 mg"},
        {"item": "DE0271", "Composición": "ASPARTATO DE ARGININA 5.000000 g"},
        {"item": "DE9999", "Composición": ""},  # producto sin composición
    ])

    df_long = expand_composition_to_rows(df_demo)
    print(df_long.to_string(index=False))

    print("\n" + "=" * 70)
    print("REPORTE DE CALIDAD")
    print("=" * 70)
    report = parser_quality_report(df_demo, df_long)
    for k, v in report.items():
        print(f"  {k}: {v}")
