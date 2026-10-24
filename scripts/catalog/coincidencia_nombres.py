"""Comparacion de nombres comerciales contra nombres de producto DIGEMID.

DIGEMID registra muchos productos importados con el nombre en ingles ("VITAMIN C 1000 mg",
"MAGNESIUM GLYCINATE") y usa codigos cortos ("D3", "B1", "ZN"). Para decidir si un nombre comercial
y un nombre DIGEMID se refieren al mismo producto se comparan tokens alfanumericos (no solo palabras)
y se normalizan los nombres de nutrientes mas comunes entre espanol e ingles.
"""

from __future__ import annotations

import re
import unicodedata

UNIT_TOKENS = frozenset({"MG", "MCG", "UG", "UI", "IU", "ML", "GR", "KG", "UN", "UND", "CAP", "CAPS", "TAB", "TABS", "CT", "OZ"})
PACKAGING_TOKENS = frozenset(
    {
        "CON", "PARA", "LOS", "LAS", "DEL", "POR", "THE", "AND", "PLUS", "WITH", "FROM", "FRASCO", "CAJA", "LATA",
        "POTE", "SOBRE", "SOBRES", "BOLSA", "TUBO", "PACK", "TABLETAS", "TABLETA", "CAPSULAS", "CAPSULA", "COMPRIMIDO",
        "COMPRIMIDOS", "SOFTGELS", "SOFTGEL", "GOMITAS", "UNIDADES", "BLANDAS", "BLANDA", "MASTICABLES", "POLVO",
        "SABOR", "VAINILLA", "FRESA", "CHOCOLATE", "NARANJA",
    }
)

# Equivalencias ES -> forma canonica compartida (se aplica a ambos lados).
NUTRIENT_SYNONYMS: dict[str, str] = {
    "VITAMINA": "VITAMIN", "VITAMINAS": "VITAMIN", "VITAMINS": "VITAMIN",
    "CALCIO": "CALCIUM", "MAGNESIO": "MAGNESIUM", "ZINC": "ZN", "HIERRO": "IRON", "POTASIO": "POTASSIUM",
    "SELENIO": "SELENIUM", "CROMO": "CHROMIUM", "YODO": "IODINE", "COBRE": "COPPER", "MANGANESO": "MANGANESE",
    "COLAGENO": "COLLAGEN", "BIOTINA": "BIOTIN", "LUTEINA": "LUTEIN", "ZEAXANTINA": "ZEAXANTHIN",
    "GLUCOSAMINA": "GLUCOSAMINE", "CONDROITINA": "CHONDROITIN", "CREATINA": "CREATINE", "PROTEINA": "PROTEIN",
    "GLICINATO": "GLYCINATE", "GLUCONATO": "GLUCONATE", "CITRATO": "CITRATE", "CARBONATO": "CARBONATE",
    "SULFATO": "SULFATE", "OXIDO": "OXIDE", "CLORURO": "CHLORIDE", "PICOLINATO": "PICOLINATE", "BISGLICINATO": "BISGLYCINATE",
    "COMPLEJO": "COMPLEX", "ELECTROLITOS": "ELECTROLYTES", "ACIDO": "ACID", "FOLICO": "FOLIC", "PROBIOTICOS": "PROBIOTICS",
    "PROBIOTICO": "PROBIOTICS", "ACEITE": "OIL", "PESCADO": "FISH", "HIGADO": "LIVER", "BACALAO": "COD",
    "MELATONINA": "MELATONIN", "CURCUMA": "TURMERIC", "JENGIBRE": "GINGER", "AJO": "GARLIC",
}


def _ascii_upper(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch)).upper()


def tokens_comparables(value: str | None) -> set[str]:
    """Tokens alfanumericos relevantes de un nombre, con sinonimos ES/EN unificados."""
    text = _ascii_upper(value)
    text = re.sub(r"(\d)[,. ](\d{3})\b", r"\1\2", text)  # 10,000 / 1 000 -> 10000 / 1000
    text = re.sub(r"\b([A-Z])-(\d)", r"\1\2", text)  # B-12 -> B12, D-3 -> D3
    raw = re.findall(r"[A-Z0-9]+", text)
    out: set[str] = set()
    for token in raw:
        if len(token) < 2 or token in UNIT_TOKENS or token in PACKAGING_TOKENS:
            continue
        out.add(NUTRIENT_SYNONYMS.get(token, token))
    return out


def nombres_coinciden(commercial_name: str | None, digemid_name: str | None) -> bool:
    """True si ambos nombres comparten al menos un token comparable (o el DIGEMID esta vacio)."""
    digemid_tokens = tokens_comparables(digemid_name)
    if not digemid_tokens:
        return True
    return bool(tokens_comparables(commercial_name) & digemid_tokens)
