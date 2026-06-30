from __future__ import annotations


def normalize_weight_unit(unit: str) -> str:
    clean = unit.strip().lower().replace(".", "")
    aliases = {
        "kilo": "kg",
        "kilos": "kg",
        "kilogramo": "kg",
        "kilogramos": "kg",
        "kgs": "kg",
        "gramo": "g",
        "gramos": "g",
        "gr": "g",
        "libra": "lb",
        "libras": "lb",
        "lbs": "lb",
        "pound": "lb",
        "pounds": "lb",
        "onza": "oz",
        "onzas": "oz",
        "ounce": "oz",
        "ounces": "oz",
        "stone": "st",
        "stones": "st",
    }
    normalized = aliases.get(clean, clean)
    if normalized not in {"kg", "g", "lb", "oz", "st"}:
        raise ValueError("Unidad de peso no soportada. Usa kg, g, lb, oz o stone.")
    return normalized


def weight_to_kg(value: float, unit: str) -> float:
    normalized = normalize_weight_unit(unit)
    factors = {
        "kg": 1.0,
        "g": 0.001,
        "lb": 0.45359237,
        "oz": 0.0283495231,
        "st": 6.35029318,
    }
    return round(float(value) * factors[normalized], 4)


def normalize_height_unit(unit: str) -> str:
    clean = unit.strip().lower().replace(".", "")
    aliases = {
        "centimetro": "cm",
        "centimetros": "cm",
        "centímetros": "cm",
        "metro": "m",
        "metros": "m",
        "pulgada": "in",
        "pulgadas": "in",
        "inch": "in",
        "inches": "in",
        "ft": "ft",
        "feet": "ft",
        "pie": "ft",
        "pies": "ft",
    }
    normalized = aliases.get(clean, clean)
    if normalized not in {"cm", "m", "in", "ft"}:
        raise ValueError("Unidad de talla no soportada. Usa cm, m, in o ft.")
    return normalized


def height_to_cm(value: float, unit: str) -> float:
    normalized = normalize_height_unit(unit)
    factors = {
        "cm": 1.0,
        "m": 100.0,
        "in": 2.54,
        "ft": 30.48,
    }
    return round(float(value) * factors[normalized], 2)


def age_to_range(age_years: int) -> str:
    if age_years < 18:
        return "menos_18"
    if age_years <= 30:
        return "18_30"
    if age_years <= 50:
        return "31_50"
    return "mas_50"


def weight_to_range(weight_kg: float) -> str:
    if weight_kg < 50:
        return "menos_50"
    if weight_kg <= 65:
        return "50_65"
    if weight_kg <= 80:
        return "66_80"
    return "mas_80"


def height_to_range(height_cm: float) -> str:
    if height_cm < 155:
        return "menos_155"
    if height_cm <= 165:
        return "155_165"
    if height_cm <= 175:
        return "166_175"
    return "mas_175"


def bmi(weight_kg: float, height_cm: float) -> float | None:
    if weight_kg <= 0 or height_cm <= 0:
        return None
    height_m = height_cm / 100
    return round(weight_kg / (height_m * height_m), 2)
