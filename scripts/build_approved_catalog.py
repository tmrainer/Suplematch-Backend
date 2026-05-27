from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SCRAPED = ROOT_DIR.parent / "suplematch-scraper/output/supplements_exhaustive_clean.csv"
DEFAULT_DIGEMID = ROOT_DIR / "digemid_limpio.csv"
DEFAULT_COMPONENTS = ROOT_DIR / "product_components.csv"
DEFAULT_OUTPUT = ROOT_DIR / "data/catalog/approved_catalog.csv"

EXCLUDED_COMPONENT_METHODS = {"noise", ""}
MIN_MATCH_SCORE = 85.0


def normalize_rs(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def clean(value: Any) -> str:
    return str(value or "").strip()


def parse_float(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def load_digemid(path: Path) -> dict[str, dict[str, str]]:
    rows = read_csv(path)
    by_rs: dict[str, dict[str, str]] = {}

    for row in rows:
        rs_key = normalize_rs(row.get("item"))
        if not rs_key:
            continue

        by_rs[rs_key] = row

    return by_rs


def load_components(path: Path) -> dict[str, list[dict[str, str]]]:
    rows = read_csv(path)
    by_rs: dict[str, list[dict[str, str]]] = {}

    for row in rows:
        rs_key = normalize_rs(row.get("item"))
        component_id = clean(row.get("component_id"))
        method = clean(row.get("match_method"))
        score = parse_float(row.get("match_score")) or 0.0

        if not rs_key or not component_id:
            continue

        if method in EXCLUDED_COMPONENT_METHODS:
            continue

        if score < MIN_MATCH_SCORE:
            continue

        by_rs.setdefault(rs_key, []).append(row)

    return by_rs


def build_catalog(
    scraped_path: Path,
    digemid_path: Path,
    components_path: Path,
) -> list[dict[str, Any]]:
    scraped_rows = read_csv(scraped_path)
    digemid_by_rs = load_digemid(digemid_path)
    components_by_rs = load_components(components_path)

    catalog_rows: list[dict[str, Any]] = []
    seen = set()

    for product in scraped_rows:
        rs_raw = clean(product.get("registro_sanitario"))
        rs_key = normalize_rs(rs_raw)
        price = parse_float(product.get("price"))
        availability = clean(product.get("availability")).lower()

        if not rs_key or rs_key not in digemid_by_rs:
            continue

        if rs_key not in components_by_rs:
            continue

        if price is None:
            continue

        if availability != "available":
            continue

        digemid = digemid_by_rs[rs_key]

        for component in components_by_rs[rs_key]:
            dedupe_key = (
                clean(product.get("pharmacy")).lower(),
                clean(product.get("sku")),
                rs_key,
                clean(component.get("component_id")),
                clean(component.get("ingredient")).lower(),
            )
            if dedupe_key in seen:
                continue

            seen.add(dedupe_key)
            catalog_rows.append(
                {
                    "pharmacy": clean(product.get("pharmacy")),
                    "commercial_name": clean(product.get("commercial_name")),
                    "formal_name": clean(product.get("formal_name")),
                    "registro_sanitario": rs_raw,
                    "registro_sanitario_key": rs_key,
                    "digemid_item": clean(digemid.get("item")),
                    "digemid_producto": clean(digemid.get("Producto")),
                    "digemid_distribuidor": clean(digemid.get("Distribuidor")),
                    "digemid_fabricante": clean(digemid.get("Fabricante")),
                    "digemid_forma_farmaceutica": clean(digemid.get("Forma Farmacéutica")),
                    "digemid_codigo_atc": clean(digemid.get("codigo_atc")),
                    "digemid_grupo_atc_3": clean(digemid.get("grupo_atc_3")),
                    "digemid_grupo_atc_4": clean(digemid.get("grupo_atc_4")),
                    "digemid_clasificacion": clean(digemid.get("descripcion_clasificacion")),
                    "digemid_composicion": clean(digemid.get("Composición")),
                    "component_id": clean(component.get("component_id")),
                    "ingredient": clean(component.get("ingredient")),
                    "amount": clean(component.get("amount")),
                    "unit": clean(component.get("unit")),
                    "amount_mg": clean(component.get("amount_mg")),
                    "component_match_score": clean(component.get("match_score")),
                    "component_match_method": clean(component.get("match_method")),
                    "price": price,
                    "currency": clean(product.get("currency")) or "PEN",
                    "availability": clean(product.get("availability")),
                    "url": clean(product.get("url")),
                    "sku": clean(product.get("sku")),
                    "brand": clean(product.get("brand")),
                    "source_strategy": clean(product.get("source_strategy")),
                    "regulatory_status": "digemid_match",
                }
            )

    return catalog_rows


def write_catalog(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else [
        "pharmacy",
        "commercial_name",
        "registro_sanitario",
        "component_id",
        "price",
        "availability",
        "url",
        "regulatory_status",
    ]

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Construye catalogo aprobado RS -> DIGEMID -> componentes.")
    parser.add_argument("--scraped", type=Path, default=DEFAULT_SCRAPED)
    parser.add_argument("--digemid", type=Path, default=DEFAULT_DIGEMID)
    parser.add_argument("--components", type=Path, default=DEFAULT_COMPONENTS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows = build_catalog(args.scraped, args.digemid, args.components)
    write_catalog(rows, args.out)

    product_keys = {
        (row["pharmacy"], row["sku"], row["registro_sanitario_key"])
        for row in rows
    }
    rs_keys = {row["registro_sanitario_key"] for row in rows}
    component_ids = {row["component_id"] for row in rows}

    print(f"catalog_rows={len(rows)}")
    print(f"approved_products={len(product_keys)}")
    print(f"approved_rs={len(rs_keys)}")
    print(f"component_ids={len(component_ids)}")
    print(f"out={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
