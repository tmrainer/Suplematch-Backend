"""
parser_composicion.py
=====================
Parser de la columna `Composición` del catálogo DIGEMID.

Convierte texto como:
    "ACIDO ASCORBICO 200.000000 mg ASCORBATO DE SODIO 337.440000 mg"

en una lista estructurada:
    [
        {'ingredient': 'ACIDO ASCORBICO', 'amount': 200.0, 'unit': 'mg', 'amount_mg': 200.0, 'salt_form': None},
        {'ingredient': 'ASCORBATO DE SODIO', 'amount': 337.44, 'unit': 'mg', 'amount_mg': 337.44, 'salt_form': None},
    ]

Reglas relevantes (ver tests/unit/test_catalog_parser_composicion.py):
  * Unidades de masa (mg, g, mcg/µg/ug) se convierten a mg. `kg` se reconoce como
    unidad pero NO se convierte: una dosis en kilogramos no es una dosis de
    componente sino un peso de presentación, así que `amount_mg=None`.
  * Unidades no convertibles: UI/IU, mL, %, y UFC/CFU (probióticos). Para
    probióticos la unidad se normaliza a "UFC" y `amount_mg=None`. Se admite
    notación científica "1 x 10^9 UFC".
  * Separadores de miles: coma o punto ("2,000.000000", "1.000,5") y espacio
    ("2 000 UI"). El espacio solo se acepta cuando el texto NO usa el formato
    DIGEMID de seis decimales (en ese formato un espacio separa tokens, nunca
    miles: "VITAMINA D3 100.000000 UI" no debe leerse como 3 100 UI).
  * Cabeceras de dosis "POR DOSIS 15.00 mL - ..." / "POR SOBRE 2.00 g - ..." se
    descartan: describen la porción, no un ingrediente.
  * Paréntesis que describen la sal o la forma del ingrediente
    ("ZINC (COMO SULFATO DE ZINC MONOHIDRATO) 10 mg", "(EQUIVALENTE A ...)",
    o cualquier paréntesis con una dosis adentro) no generan un ingrediente
    aparte: se guardan en `salt_form` del ingrediente al que acompañan. Otros
    paréntesis ("VITAMINA E (TOCOFEROL)", "(EPA)") se conservan en el nombre.

Uso típico:
    df_long = expand_composition_to_rows(df_digemid, id_col='item', text_col='Composición')
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
    "mcg": 0.001,
    "µg": 0.001,
    "μg": 0.001,
    "ug": 0.001,
    # Las siguientes no son convertibles a mg; se dejan como None
    "kg": None,  # peso de presentación, no dosis de componente
    "ui": None,
    "iu": None,
    "ml": None,
    "%": None,
    "UFC": None,  # unidades formadoras de colonias (probióticos)
}

# Normalización de alias de unidad -> clave de UNIT_TO_MG
UNIT_ALIASES: dict[str, str] = {
    "cfu": "UFC",
    "ufc": "UFC",
    "u.f.c.": "UFC",
    "iu": "ui",
    "u.i.": "ui",
    "μg": "µg",
}

UNITS_REGEX = r"(?:mcg|µg|μg|ug|mg|kg|g|UI|IU|U\.I\.|UFC|CFU|U\.F\.C\.|ml|mL|%)"

# Número con separadores de miles por coma/punto y decimales opcionales.
# Ej.: 2,000.000000 | 1.000,5 | 500 | 0.4 | 100,000,000.000000
_NUMBER_SEP = r"(?:\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)"
# Igual que arriba pero admitiendo espacio como separador de miles ("2 000").
# El lookbehind evita leer "D3 100" o "B12 500" como un solo número y la
# exclusión de "OMEGA " evita "OMEGA 3 500 mg" -> 3500 mg.
_NUMBER_SPACE_SEP = (
    r"(?<![A-Za-z0-9®])(?<!OMEGA )(?<!OMEGA-)(?<!omega )(?<!omega-)"
    r"\d{1,3}(?: \d{3})+(?:[.,]\d+)?"
)
NUMBER_REGEX = _NUMBER_SEP

# Notación científica opcional para UFC: "1 x 10^9", "1x10 9", "2 × 10^10"
_SCI_REGEX = r"(?:\s*[xX×]\s*10\s*(?:\^|\*\*)?\s*(\d{1,2}))?"

# Patrón principal: número (con decimales o coma) seguido de una unidad reconocida.
# El nombre del ingrediente es lo que viene ANTES de cada (número + unidad).
_DOSE_PATTERN = re.compile(
    rf"({NUMBER_REGEX}){_SCI_REGEX}\s*({UNITS_REGEX})(?![A-Za-z])",
    re.IGNORECASE,
)
_DOSE_PATTERN_SPACE_THOUSANDS = re.compile(
    rf"({_NUMBER_SPACE_SEP}|{NUMBER_REGEX}){_SCI_REGEX}\s*({UNITS_REGEX})(?![A-Za-z])",
    re.IGNORECASE,
)

# Formato DIGEMID: todas las cantidades llevan seis decimales ("400.000000 UI").
_DIGEMID_DECIMALS = re.compile(r"\d\.\d{6}(?!\d)")

# Cabecera de porción: "POR DOSIS 15.00 mL - ", "POR SOBRE 11.40 - ", "POR MILILITRO mL - "
_SERVING_HEADER = re.compile(r"^\s*(?:POR|CADA)\b[^-]*?\s-\s+", re.IGNORECASE)
_SERVING_NAME = re.compile(r"^(?:POR|CADA)\b", re.IGNORECASE)

# Paréntesis que describen sal/forma química o contienen una dosis propia.
_PAREN = re.compile(r"\(([^()]*)\)")
_SALT_PREFIX = re.compile(
    r"^\s*(?:COMO|EN FORMA DE|EQUIV(?:ALENTE)?\.?(?:\s+A)?|APORTA(?:NDO)?|PROVENIENTE DE)\b",
    re.IGNORECASE,
)
_MARKER = "\x00"
_MARKER_RE = re.compile(rf"{_MARKER}(\d+){_MARKER}")


# ---------------------------------------------------------------------------
# Funciones principales
# ---------------------------------------------------------------------------

def parse_composition(text: str) -> list[dict]:
    """
    Parsea un string de composición farmacéutica de DIGEMID.

    Estrategia:
      1. Descartar la cabecera de porción ("POR DOSIS 15.00 mL - ").
      2. Sustituir los paréntesis de sal/forma por marcadores para que su
         dosis interna no genere un ingrediente aparte.
      3. Encontrar todas las posiciones donde aparece (NÚMERO + UNIDAD).
      4. El nombre del ingrediente es el texto entre el final del match anterior
         y el inicio del match actual. Esto permite que los nombres incluyan
         dígitos (ej. "VITAMINA B12") sin confundirse con la dosis.

    Returns
    -------
    list of dict
        Cada elemento tiene las keys: 'ingredient', 'amount', 'unit',
        'amount_mg' y 'salt_form'. 'amount_mg' es None si la unidad no es
        convertible a mg. 'salt_form' es None si no hay paréntesis de sal.
    """
    if not isinstance(text, str) or not text.strip():
        return []

    body = _SERVING_HEADER.sub("", text, count=1)
    body, salts = _extract_salt_forms(body)

    pattern = _DOSE_PATTERN if _DIGEMID_DECIMALS.search(body) else _DOSE_PATTERN_SPACE_THOUSANDS
    matches = list(pattern.finditer(body))
    if not matches:
        return []

    results = []
    last_end = 0

    for m in matches:
        raw_name = body[last_end:m.start()]
        trailing_salt, salt_form = _split_salt_forms(raw_name, salts)
        if trailing_salt and results:
            # "ZINC 10 mg (COMO SULFATO DE ZINC 27.5 mg)": el paréntesis va
            # después de la dosis y describe al ingrediente anterior.
            previous = results[-1]
            previous["salt_form"] = "; ".join(filter(None, [previous["salt_form"], trailing_salt]))
        elif trailing_salt:
            salt_form = "; ".join(filter(None, [trailing_salt, salt_form]))
        name = _clean_ingredient_name(_MARKER_RE.sub(" ", raw_name))
        last_end = m.end()

        if not name or _SERVING_NAME.match(name):
            # nombre vacío (inicio del string) o resto de cabecera de porción
            continue

        amount = _parse_number(m.group(1))
        exponent = m.group(2)
        if exponent:
            amount *= 10 ** int(exponent)
        unit = _normalize_unit(m.group(3))
        mg_factor = UNIT_TO_MG.get(unit)
        amount_mg = amount * mg_factor if mg_factor is not None else None

        results.append({
            "ingredient": name,
            "amount": amount,
            "unit": unit,
            "amount_mg": amount_mg,
            "salt_form": salt_form,
        })

    # Paréntesis de sal al final del texto ("HIERRO 60 mg (EQUIVALENTE A ...)")
    tail_salt, _ = _split_salt_forms(body[last_end:], salts)
    if tail_salt and results:
        results[-1]["salt_form"] = "; ".join(filter(None, [results[-1]["salt_form"], tail_salt]))

    return results


def _normalize_unit(raw_unit: str) -> str:
    unit = raw_unit.strip()
    lowered = unit.lower()
    if lowered in UNIT_ALIASES:
        return UNIT_ALIASES[lowered]
    if lowered in UNIT_TO_MG:
        return lowered
    return unit


def _extract_salt_forms(text: str) -> tuple[str, dict[int, str]]:
    """Reemplaza paréntesis de sal/forma (o con dosis adentro) por marcadores."""
    salts: dict[int, str] = {}

    def _replace(match: re.Match) -> str:
        inner = match.group(1)
        if _SALT_PREFIX.match(inner) or _DOSE_PATTERN.search(inner):
            index = len(salts)
            salts[index] = re.sub(r"\s+", " ", inner).strip(" ,.;:-").upper()
            return f" {_MARKER}{index}{_MARKER} "
        return match.group(0)

    return _PAREN.sub(_replace, text), salts


def _split_salt_forms(raw_name: str, salts: dict[int, str]) -> tuple[Optional[str], Optional[str]]:
    """Separa los marcadores de sal que preceden al nombre (pertenecen al
    ingrediente anterior) de los que van dentro/después del nombre (propios)."""
    leading: list[str] = []
    own: list[str] = []
    seen_text = False
    for token in re.split(rf"({_MARKER}\d+{_MARKER})", raw_name):
        marker = _MARKER_RE.fullmatch(token)
        if marker:
            salt = salts.get(int(marker.group(1)))
            if salt:
                (own if seen_text else leading).append(salt)
        elif token.strip(" ,.;:-"):
            seen_text = True
    return ("; ".join(leading) or None), ("; ".join(own) or None)


def _clean_ingredient_name(name: str) -> str:
    """Limpieza básica del nombre de ingrediente parseado."""
    # Eliminar signos de puntuación al inicio o final
    name = name.strip(" ,.;:-")
    # Colapsar espacios múltiples
    name = re.sub(r"\s+", " ", name)
    # Mantener en mayúsculas (consistente con DIGEMID)
    return name.upper()


def _parse_number(value: str) -> float:
    text = str(value).strip()
    if " " in text:
        # Separador de miles con espacio: "2 000" / "2 000,5"
        text = text.replace(" ", "")
    if "," in text and "." in text:
        if text.rfind(",") < text.rfind("."):
            text = text.replace(",", "")
        else:
            text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        parts = text.split(",")
        if len(parts) > 1 and all(len(part) == 3 for part in parts[1:]):
            text = "".join(parts)
        else:
            text = text.replace(",", ".")
    elif text.count(".") > 1:
        parts = text.split(".")
        if all(len(part) == 3 for part in parts[1:]):
            text = "".join(parts)
    return float(text)


def expand_composition_to_rows(
    df: pd.DataFrame,
    id_col: str = "item",
    text_col: str = "Composición",
) -> pd.DataFrame:
    """
    Aplica el parser a un DataFrame entero y devuelve formato 'long':
    una fila por (producto, ingrediente).

    Returns
    -------
    pd.DataFrame
        Columnas: [id_col, ingredient, amount, unit, amount_mg, salt_form]
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
                "salt_form": None,
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
# Demo con los ejemplos visibles del dataset (los tests viven en tests/unit)
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
        ("PARACETAMOL 500 mg CAFEINA 65 mg", 2),
        ("MALATO DE CITRULINA 4,000.000000 mg CREATINA MONOHIDRATO 3,250.000000 mg", 2),
        # Probióticos y cabecera de porción
        ("POR SOBRE 15.00 g - L-GLUTAMINA 10.000000 g LACTOBACILLUS REUTERI 100,000,000.000000 UFC", 2),
        ("VITAMINA D 2 000 UI", 1),
        ("ZINC (COMO SULFATO DE ZINC MONOHIDRATO) 10 mg", 1),
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
            salt = f" [{ing['salt_form']}]" if ing["salt_form"] else ""
            print(f"    - {ing['ingredient']}{salt}: {ing['amount']} {ing['unit']}  →  {mg}")

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
