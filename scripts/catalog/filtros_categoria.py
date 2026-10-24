"""Filtros de categoria para el catalogo comercial.

Un producto solo puede entrar al catalogo aprobado si es un suplemento oral.
Cosmeticos, topicos, higiene y productos de uso externo se rechazan aunque
tengan un registro sanitario DIGEMID asociado, porque la asociacion suele ser
un falso positivo del matching por nombre (ej. "Pantene Pro-V" -> RS "PRO").
"""

from __future__ import annotations

import re
import unicodedata

# Palabras o frases que identifican un producto que NO es suplemento oral.
NON_SUPPLEMENT_PATTERNS: tuple[tuple[str, str], ...] = (
    ("capilar", r"\b(shampoo|champu|acondicionador|leave[- ]?in|mascarilla capilar|tonico capilar|tinte|crema para peinar|serum capilar|anticaida)\b"),
    ("cosmetico", r"\b(crema (?:facial|corporal|hidratante|antiarrugas|antiedad|de manos|de pies|contorno)|serum facial|locion|maquillaje|labial|esmalte|perfume|colonia|desodorante|antitranspirante|exfoliante|mascarilla facial|crema\b.*\b(?:ml|gr?)\b)"),
    ("higiene", r"\b(jabon|gel de ducha|gel de bano|enjuague bucal|pasta dental|dentifrico|toallitas|panales?|talco|hilo dental)\b"),
    ("topico", r"\b(protector solar|bloqueador|pomada|unguento|gel topico|parche|spray nasal|gotas (?:oftalmicas|oticas|nasales)|colirio|supositorio|ovulo)\b"),
    ("bebe_formula", r"\b(formula infantil|leche de formula|babylac|nan optipro|similac|enfamil|nutrilon)\b"),
)

# Marcas de cuidado personal que nunca son suplementos.
NON_SUPPLEMENT_BRANDS: frozenset[str] = frozenset(
    {
        "pantene", "sedal", "wella", "dove", "head shoulders", "head & shoulders", "tresemme",
        "elvive", "loreal", "l oreal", "nivea", "ponds", "neutrogena", "eucerin", "cetaphil",
        "isdin", "la roche posay", "garnier", "savital", "konzil", "anian", "difeel", "herbal essences",
        "colgate", "oral b", "listerine", "rexona", "axe", "johnson s", "huggies", "pampers", "babysec",
    }
)

_UNITS_ONLY_TOPICAL = re.compile(r"\b(?:tubo|sachet)\b.*\b\d+\s*(?:ml|g|gr)\b")


def _normalize(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9&% ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def categoria_no_suplemento(*fields: str | None) -> str:
    """Devuelve el motivo si el producto no es un suplemento oral; cadena vacia si parece suplemento."""
    text = _normalize(" ".join(str(field or "") for field in fields))
    if not text:
        return ""

    for brand in NON_SUPPLEMENT_BRANDS:
        if re.search(rf"\b{re.escape(brand)}\b", text):
            return f"marca_no_suplemento:{brand.replace(' ', '_')}"

    for label, pattern in NON_SUPPLEMENT_PATTERNS:
        if re.search(pattern, text):
            return label

    return ""


def es_suplemento_oral(*fields: str | None) -> bool:
    return categoria_no_suplemento(*fields) == ""
