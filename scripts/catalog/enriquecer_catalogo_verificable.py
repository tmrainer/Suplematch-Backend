from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VERIFICATION_COLUMNS = [
    "contains_fish",
    "contains_fish_inferred",
    "contains_shellfish",
    "contains_shellfish_inferred",
    "contains_gelatin",
    "contains_gelatin_inferred",
    "softgel_verified",
    "softgel_inferred",
    "contains_dairy",
    "contains_dairy_inferred",
    "contains_lactose",
    "contains_lactose_inferred",
    "contains_soy",
    "contains_soy_inferred",
    "contains_soya",
    "contains_soya_inferred",
    "gluten_free_verified",
    "gluten_free_inferred",
    "label_status",
    "label_verified_at",
    "label_verification_source",
    "label_verification_notes",
    "restriction_traceability_level",
    "brand_confidence",
    "brand_source",
    "amount_source",
    "serving_size",
    "units_per_pack",
    "commercial_confidence_score",
    "commercial_confidence_level",
    "commercial_confidence_reasons",
]

RECOMMENDABLE_COMPONENTS = Path("data/knowledge/condition_component_links.csv")

COMPONENT_GROUP_TERMS = {
    "omega_3": ("omega", "epa", "dha", "aceite_de_pescado"),
    "probioticos": (
        "probiotico",
        "probioticos",
        "lactobacillus",
        "bifidobacterium",
        "bacillus",
        "saccharomyces",
    ),
}

KNOWN_BRANDS = (
    "21st Century",
    "Abejita",
    "Bayer",
    "Carbocalcio",
    "Centrum",
    "Diutin",
    "Drasanvi",
    "Ensure",
    "Epadex",
    "Fisiotech",
    "Garden House",
    "German Energy",
    "Gestafol",
    "GNC",
    "Mason",
    "Mason Natural",
    "Nature Made",
    "Nature's Bounty",
    "Natrol",
    "NOW",
    "Omeganatur",
    "Pharmaton",
    "Redoxon",
    "Solgar",
    "Sunvit",
    "Supradyn",
    "Swanson",
    "Vitafusion",
)

GENERIC_BRAND_STARTS = {
    "acido",
    "ácido",
    "calcio",
    "citrato",
    "colageno",
    "colágeno",
    "complejo",
    "creatina",
    "dha",
    "epa",
    "hierro",
    "magnesio",
    "melatonina",
    "omega",
    "probiótico",
    "probiotico",
    "proteina",
    "proteína",
    "vitamina",
    "vitaminas",
    "zinc",
}

PACK_UNIT_PATTERN = re.compile(
    r"\b(?:x\s*)?(\d{1,4})\s*(capsulas?|c[aá]psulas?|cap\.?|tabletas?|tabs?|comprimidos?|sobres?|"
    r"ampollas?|unidades?|unds?|und|un|gomitas?|gomas?|sachets?|softgels?|sticks?)\b",
    flags=re.IGNORECASE,
)

AMOUNT_PATTERN = re.compile(
    r"(?<!\d)(\d{1,5}(?:[.,]\d{1,4})?)\s*(mg|mcg|µg|ug|g|ui|iu|u\.i\.|u i)\b",
    flags=re.IGNORECASE,
)

UNIT_TO_MG = {
    "g": 1000.0,
    "mg": 1.0,
    "mcg": 0.001,
    "ug": 0.001,
    "µg": 0.001,
}


def clean(value: Any) -> str:
    return str(value or "").strip()


def normalize_text(*values: Any) -> str:
    text = " ".join(clean(value) for value in values if clean(value))
    text = text.lower()
    text = (
        text.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ü", "u")
    )
    return text


def normalize_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", clean(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    return text


def truthy(flag: bool) -> str:
    return "true" if flag else ""


def boolish(value: Any) -> bool:
    return clean(value).lower() in {"1", "true", "yes", "si", "sí", "verified"}


def available(value: Any) -> bool:
    return clean(value).lower() in {"available", "in_stock", "stock"}


def has_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def parse_number(value: Any) -> float | None:
    text = clean(value).replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def normalize_unit(unit: Any) -> str:
    text = clean(unit).lower().replace("u.i.", "ui").replace("u i", "ui")
    if text == "μg":
        text = "µg"
    return text


def amount_to_mg(amount: float, unit: str, component_id: str, ingredient: str) -> float | None:
    normalized_unit = normalize_unit(unit)
    if normalized_unit in UNIT_TO_MG:
        return amount * UNIT_TO_MG[normalized_unit]

    component_text = normalize_text(component_id, ingredient)
    if normalized_unit in {"ui", "iu"}:
        if (
            "vitamina d" in component_text
            or "vitamin d" in component_text
            or "colecalciferol" in component_text
            or "ergocalciferol" in component_text
        ):
            return amount * 0.000025
        if "vitamina e" in component_text or "vitamin e" in component_text or "tocofer" in component_text:
            return amount * 0.67
        if "vitamina a" in component_text or "vitamin a" in component_text or "retinol" in component_text:
            return amount * 0.0003

    return None


def infer_amount(row: dict[str, str]) -> tuple[str, str, str, str]:
    amount = clean(row.get("amount"))
    unit = clean(row.get("unit"))
    amount_mg = clean(row.get("amount_mg"))
    source = clean(row.get("amount_source"))

    parsed_amount = parse_number(amount)
    if parsed_amount is not None and unit and not amount_mg:
        converted = amount_to_mg(parsed_amount, unit, clean(row.get("component_id")), clean(row.get("ingredient")))
        if converted is not None:
            return amount, unit, f"{converted:.6g}", source or "component_amount_conversion"

    if amount and unit and amount_mg:
        return amount, unit, amount_mg, source or "component_parser"

    text = normalize_text(
        row.get("commercial_name"),
        row.get("formal_name"),
        row.get("digemid_producto"),
        row.get("digemid_composicion"),
    )
    matches = list(AMOUNT_PATTERN.finditer(text))
    if not matches:
        return amount, unit, amount_mg, source

    component_text = normalize_text(row.get("ingredient"), row.get("component_id"))
    preferred = matches[0]
    for match in matches:
        window_start = max(0, match.start() - 45)
        window_end = min(len(text), match.end() + 45)
        window = text[window_start:window_end]
        ingredient_tokens = [token for token in re.split(r"\W+", component_text) if len(token) >= 4]
        if any(token in window for token in ingredient_tokens[:4]):
            preferred = match
            break

    inferred_amount = preferred.group(1).replace(",", ".")
    inferred_unit = normalize_unit(preferred.group(2))
    parsed = parse_number(inferred_amount)
    converted = amount_to_mg(parsed, inferred_unit, clean(row.get("component_id")), clean(row.get("ingredient"))) if parsed is not None else None

    return (
        amount or inferred_amount,
        unit or inferred_unit,
        amount_mg or (f"{converted:.6g}" if converted is not None else ""),
        source or "catalog_text_regex",
    )


def infer_pack_size(row: dict[str, str]) -> tuple[str, str]:
    serving_size = clean(row.get("serving_size"))
    units_per_pack = clean(row.get("units_per_pack"))
    if serving_size and units_per_pack:
        return serving_size, units_per_pack

    text = normalize_text(row.get("commercial_name"), row.get("formal_name"), row.get("digemid_producto"))
    match = PACK_UNIT_PATTERN.search(text)
    if not match:
        return serving_size, units_per_pack

    return serving_size or f"{match.group(1)} {match.group(2)}", units_per_pack or match.group(1)


def infer_brand(row: dict[str, str]) -> tuple[str, str, str]:
    brand = clean(row.get("brand"))
    confidence = clean(row.get("brand_confidence"))
    source = clean(row.get("brand_source"))
    if brand:
        return brand, confidence or "high", source or "source_field"

    name = clean(row.get("commercial_name")) or clean(row.get("formal_name"))
    if not name:
        return "", confidence, source

    normalized_name = normalize_text(name)
    for known in KNOWN_BRANDS:
        if normalized_name.startswith(normalize_text(known)):
            return known, "high", "known_brand_prefix"

    first_word = re.split(r"\s+", name.strip(), maxsplit=1)[0].strip(" -")
    if normalize_key(first_word) and normalize_key(first_word) not in {normalize_key(v) for v in GENERIC_BRAND_STARTS}:
        return first_word, "medium", "commercial_name_prefix"

    return "", confidence, source


def commercial_confidence(row: dict[str, str]) -> tuple[str, str, str]:
    score = 0.0
    reasons: list[str] = []

    if clean(row.get("registro_sanitario")):
        source = clean(row.get("registro_sanitario_source"))
        if source == "digemid_name_match":
            score += 0.18
            reasons.append("RS inferido por DIGEMID/nombre")
        elif source == "image_ocr":
            score += 0.20
            reasons.append("RS recuperado por OCR de etiqueta")
        else:
            score += 0.28
            reasons.append("RS informado y trazable")

    regulatory = normalize_text(row.get("regulatory_status"), row.get("component_traceable"))
    if "digemid_match" in regulatory or "true_rs_component" in regulatory:
        score += 0.22
        reasons.append("Componente validado contra RS")
    elif "component" in regulatory:
        score += 0.14
        reasons.append("Componente detectado por nombre")

    if parse_number(row.get("price")) is not None:
        score += 0.14
        reasons.append("Precio válido")

    if available(row.get("availability")):
        score += 0.12
        reasons.append("Disponible en farmacia")

    if clean(row.get("amount")) and clean(row.get("unit")):
        score += 0.08
        reasons.append("Dosis declarada")

    if clean(row.get("label_verification_source")):
        score += 0.10
        reasons.append("Etiqueta/fuente verificada")
    elif clean(row.get("restriction_traceability_level")) == "inferred":
        score += 0.04
        reasons.append("Restricciones inferidas")

    if clean(row.get("brand")):
        score += 0.04
        reasons.append("Marca identificada")

    try:
        component_match = float(row.get("component_match_score") or 0.0)
    except ValueError:
        component_match = 0.0
    if component_match >= 95:
        score += 0.04
        reasons.append("Match de componente alto")
    elif component_match >= 85:
        score += 0.02
        reasons.append("Match de componente aceptable")

    score = max(0.0, min(1.0, score))
    if score >= 0.85:
        level = "alta"
    elif score >= 0.68:
        level = "media"
    else:
        level = "baja"
    return f"{score:.4f}", level, ";".join(reasons[:8])


def infer_restrictions_from_text(row: dict[str, str]) -> dict[str, bool]:
    text = normalize_text(row.get("commercial_name"), row.get("formal_name"), row.get("digemid_producto"), row.get("url"))
    return {
        "contains_fish": has_any(text, (r"\bfish oil\b", r"\bpescado\b", r"\bomega\s*3\b", r"\bepa\b", r"\bdha\b", r"\bkrill\b")),
        "contains_shellfish": has_any(text, (r"\bmariscos?\b", r"\bcrustaceos?\b", r"\bshellfish\b", r"\bkrill\b")),
        "contains_gelatin": has_any(text, (r"\bcapsulas? blandas?\b", r"\bsoftgel\b", r"\bgelatina\b", r"\bgelatin\b")),
        "softgel": has_any(text, (r"\bcapsulas? blandas?\b", r"\bsoftgel\b")),
        "contains_lactose": has_any(text, (r"\blactosa\b", r"\blactose\b")),
        "contains_dairy": has_any(text, (r"\bwhey\b", r"\bsuero de leche\b", r"\bleche\b", r"\bcaseina\b", r"\bcasein\b")),
        "contains_soy": has_any(text, (r"\bsoya\b", r"\bsoy\b", r"\blecitina de soya\b", r"\bsoy lecithin\b")),
        "gluten_free": has_any(text, (r"\bsin gluten\b", r"\bgluten free\b", r"\blibre de gluten\b")),
    }


def enrich_row(row: dict[str, str], verified_at: str) -> dict[str, str]:
    enriched = dict(row)
    official_composition = normalize_text(
        row.get("digemid_composicion"),
        row.get("digemid_producto"),
        row.get("digemid_clasificacion"),
    )
    official_form = normalize_text(row.get("digemid_forma_farmaceutica"))
    explicit = normalize_text(
        row.get("contains_fish"),
        row.get("contains_shellfish"),
        row.get("contains_gelatin"),
        row.get("contains_dairy"),
        row.get("contains_lactose"),
        row.get("contains_soy"),
        row.get("contains_soya"),
        row.get("gluten_free_verified"),
    )
    inferred_text = infer_restrictions_from_text(row)

    contains_fish = has_any(
        official_composition,
        (
            r"\baceite de pescado\b",
            r"\bpescado\b",
            r"\bfish oil\b",
            r"\bomega\s*3\s+marino\b",
            r"\bacidos? grasos? de pescado\b",
        ),
    )
    contains_shellfish = has_any(
        official_composition,
        (
            r"\bmariscos?\b",
            r"\bcrustaceos?\b",
            r"\bshellfish\b",
            r"\bkrill\b",
        ),
    )
    softgel_verified = has_any(
        official_form,
        (
            r"\bcapsula blanda\b",
            r"\bcapsulas blandas\b",
            r"\bsoftgel\b",
        ),
    )
    contains_gelatin = softgel_verified or has_any(
        official_composition,
        (
            r"\bgelatina\b",
            r"\bgelatin\b",
        ),
    )
    contains_lactose = has_any(
        official_composition,
        (
            r"\blactosa\b",
            r"\blactose\b",
        ),
    )
    contains_dairy = contains_lactose or has_any(
        official_composition,
        (
            r"\bleche\b",
            r"\bsuero de leche\b",
            r"\bwhey\b",
            r"\bcaseina\b",
            r"\bcasein\b",
        ),
    )
    contains_soy = has_any(
        official_composition,
        (
            r"\bsoya\b",
            r"\bsoy\b",
            r"\blecitina de soya\b",
            r"\bsoy lecithin\b",
        ),
    )

    gluten_free_verified = "gluten_free_verified" in row and clean(row.get("gluten_free_verified")).lower() in {
        "1",
        "true",
        "yes",
        "si",
        "sí",
        "verified",
    }
    if "gluten" in explicit and "free" in explicit:
        gluten_free_verified = True

    flags = {
        "contains_fish": contains_fish,
        "contains_shellfish": contains_shellfish,
        "contains_gelatin": contains_gelatin,
        "softgel_verified": softgel_verified,
        "contains_dairy": contains_dairy,
        "contains_lactose": contains_lactose,
        "contains_soy": contains_soy,
        "contains_soya": contains_soy,
        "gluten_free_verified": gluten_free_verified,
    }
    for key, value in flags.items():
        if not clean(enriched.get(key)):
            enriched[key] = truthy(value)

    inferred_flags = {
        "contains_fish_inferred": inferred_text["contains_fish"],
        "contains_shellfish_inferred": inferred_text["contains_shellfish"],
        "contains_gelatin_inferred": inferred_text["contains_gelatin"],
        "softgel_inferred": inferred_text["softgel"],
        "contains_dairy_inferred": inferred_text["contains_dairy"],
        "contains_lactose_inferred": inferred_text["contains_lactose"],
        "contains_soy_inferred": inferred_text["contains_soy"],
        "contains_soya_inferred": inferred_text["contains_soy"],
        "gluten_free_inferred": inferred_text["gluten_free"],
    }
    for key, value in inferred_flags.items():
        if not clean(enriched.get(key)):
            enriched[key] = truthy(value)

    detected = [key for key, value in flags.items() if value]
    if detected and not clean(enriched.get("label_verification_source")):
        sources = []
        if official_composition:
            sources.append("digemid_composicion")
        if official_form:
            sources.append("digemid_forma_farmaceutica")
        enriched["label_verification_source"] = "+".join(sources) or "catalog_explicit_fields"
    if detected and not clean(enriched.get("label_verified_at")):
        enriched["label_verified_at"] = verified_at
    if detected and not clean(enriched.get("label_verification_notes")):
        enriched["label_verification_notes"] = "flags verificados por campos regulatorios disponibles"

    inferred_detected = [key for key, value in inferred_flags.items() if value]
    if detected:
        enriched["label_status"] = clean(enriched.get("label_status")) or "verified"
        enriched["restriction_traceability_level"] = clean(enriched.get("restriction_traceability_level")) or "verified"
    elif inferred_detected:
        enriched["label_status"] = clean(enriched.get("label_status")) or "inferred"
        enriched["restriction_traceability_level"] = clean(enriched.get("restriction_traceability_level")) or "inferred"
        if not clean(enriched.get("label_verification_notes")):
            enriched["label_verification_notes"] = "restricciones inferidas por texto comercial; revisar etiqueta antes de afirmar"
    else:
        enriched["label_status"] = clean(enriched.get("label_status")) or "unknown"
        enriched["restriction_traceability_level"] = clean(enriched.get("restriction_traceability_level")) or "unknown"

    amount, unit, amount_mg, amount_source = infer_amount(enriched)
    enriched["amount"] = amount
    enriched["unit"] = unit
    enriched["amount_mg"] = amount_mg
    if amount_source:
        enriched["amount_source"] = amount_source

    serving_size, units_per_pack = infer_pack_size(enriched)
    if serving_size:
        enriched["serving_size"] = serving_size
    if units_per_pack:
        enriched["units_per_pack"] = units_per_pack

    brand, brand_confidence, brand_source = infer_brand(enriched)
    enriched["brand"] = brand
    if brand_confidence:
        enriched["brand_confidence"] = brand_confidence
    if brand_source:
        enriched["brand_source"] = brand_source

    confidence_score, confidence_level, confidence_reasons = commercial_confidence(enriched)
    enriched["commercial_confidence_score"] = confidence_score
    enriched["commercial_confidence_level"] = confidence_level
    enriched["commercial_confidence_reasons"] = confidence_reasons

    return enriched


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_rows(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def row_key(row: dict[str, str]) -> str:
    return "|".join(
        clean(row.get(key))
        for key in ("pharmacy", "sku", "commercial_name", "registro_sanitario")
    )


def product_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    products: list[dict[str, str]] = []
    for row in rows:
        key = row_key(row)
        if key in seen:
            continue
        seen.add(key)
        products.append(row)
    return products


def write_subset(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    selected = [
        "pharmacy",
        "commercial_name",
        "brand",
        "brand_confidence",
        "registro_sanitario",
        "component_id",
        "ingredient",
        "amount",
        "unit",
        "amount_mg",
        "amount_source",
        "price",
        "url",
        "label_status",
        "restriction_traceability_level",
    ]
    fieldnames = [column for column in selected if column in columns]
    write_rows(path, fieldnames, [{key: row.get(key, "") for key in fieldnames} for row in rows])


def load_recommendable_components(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return {
            clean(row.get("component"))
            for row in csv.DictReader(handle)
            if clean(row.get("component"))
        }


def has_catalog_component(component: str, catalog_component_keys: set[str]) -> bool:
    key = normalize_key(component)
    if not key:
        return False
    if key in catalog_component_keys:
        return True
    group_terms = COMPONENT_GROUP_TERMS.get(key, ())
    return any(
        key in catalog_key
        or catalog_key in key
        or any(term in catalog_key for term in group_terms)
        for catalog_key in catalog_component_keys
    )


def write_quality_reports(
    rows: list[dict[str, str]],
    columns: list[str],
    report_dir: Path,
    recommendable_components_path: Path,
) -> dict[str, Any]:
    report_dir.mkdir(parents=True, exist_ok=True)
    products = product_rows(rows)

    missing_amount = [row for row in rows if not clean(row.get("amount")) or not clean(row.get("unit"))]
    missing_amount_mg = [row for row in rows if not clean(row.get("amount_mg"))]
    missing_brand = [row for row in products if not clean(row.get("brand"))]
    incomplete_restrictions = [
        row
        for row in products
        if clean(row.get("restriction_traceability_level")) in {"", "unknown", "inferred"}
    ]

    component_product_keys: dict[str, set[str]] = {}
    component_names: dict[str, str] = {}
    for row in rows:
        component_id = clean(row.get("component_id"))
        if not component_id:
            continue
        component_product_keys.setdefault(component_id, set()).add(row_key(row))
        component_names.setdefault(component_id, clean(row.get("ingredient")) or component_id)

    weak_components = [
        {
            "component_id": component_id,
            "ingredient": component_names.get(component_id, component_id),
            "product_count": str(len(keys)),
            "status": "sin_producto" if len(keys) == 0 else "menos_de_3_productos",
        }
        for component_id, keys in sorted(component_product_keys.items(), key=lambda item: (len(item[1]), item[0]))
        if len(keys) < 3
    ]

    recommendable = load_recommendable_components(recommendable_components_path)
    catalog_component_names = {normalize_key(row.get("ingredient")) for row in rows if clean(row.get("ingredient"))}
    missing_recommendable = [
        {
            "component": component,
            "status": "sin_producto_en_catalogo_aprobado",
        }
        for component in sorted(recommendable)
        if not has_catalog_component(component, catalog_component_names)
    ]

    write_subset(report_dir / "productos_sin_dosis.csv", columns, missing_amount)
    write_subset(report_dir / "productos_sin_amount_mg.csv", columns, missing_amount_mg)
    write_subset(report_dir / "productos_sin_marca.csv", columns, missing_brand)
    write_subset(report_dir / "productos_restricciones_incompletas.csv", columns, incomplete_restrictions)
    write_rows(report_dir / "componentes_con_menos_de_3_productos.csv", ["component_id", "ingredient", "product_count", "status"], weak_components)
    write_rows(report_dir / "componentes_recomendables_sin_producto.csv", ["component", "status"], missing_recommendable)

    summary = {
        "rows": len(rows),
        "products": len(products),
        "missing_amount_rows": len(missing_amount),
        "missing_amount_mg_rows": len(missing_amount_mg),
        "missing_brand_products": len(missing_brand),
        "incomplete_restriction_products": len(incomplete_restrictions),
        "weak_components": len(weak_components),
        "recommendable_components_without_product": len(missing_recommendable),
        "report_dir": str(report_dir),
    }
    (report_dir / "catalog_quality_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Enriquece el catálogo aprobado con dosis, marca, flags y reportes de calidad.")
    parser.add_argument("--input", type=Path, default=Path("data/catalog/approved_catalog.csv"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report-dir", type=Path, default=Path("data/reports/catalog_quality"))
    parser.add_argument("--recommendable-components", type=Path, default=RECOMMENDABLE_COMPONENTS)
    args = parser.parse_args()

    columns, rows = read_rows(args.input)
    out_path = args.output or args.input
    verified_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    final_columns = list(columns)
    for column in VERIFICATION_COLUMNS:
        if column not in final_columns:
            final_columns.append(column)

    enriched_rows = [enrich_row(row, verified_at) for row in rows]
    write_rows(out_path, final_columns, enriched_rows)
    summary = write_quality_reports(enriched_rows, final_columns, args.report_dir, args.recommendable_components)

    verified_rows = sum(1 for row in enriched_rows if clean(row.get("label_verification_source")))
    flagged_rows = sum(
        1
        for row in enriched_rows
        if any(clean(row.get(column)) for column in VERIFICATION_COLUMNS[:9])
    )
    print(
        f"catalog_enrichment=ok rows={len(enriched_rows)} "
        f"flagged_rows={flagged_rows} verified_source_rows={verified_rows} "
        f"missing_amount_rows={summary['missing_amount_rows']} "
        f"missing_brand_products={summary['missing_brand_products']} "
        f"output={out_path} report_dir={args.report_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
