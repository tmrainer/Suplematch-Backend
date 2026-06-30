from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from app.ml.runtime.modelo2_inference import (  # noqa: E402
    COMPONENT_ALIASES,
    COMPONENT_DISPLAY_BY_ID,
    COMPONENT_ID_OVERRIDES,
    _normalize_text,
)


DEFAULT_LINKS = ROOT_DIR / "data/knowledge/condition_component_links.csv"
DEFAULT_MASTER = ROOT_DIR / "data/training/supplement_model/Component_Master_Clean.csv"
DEFAULT_CATALOG = ROOT_DIR / "data/catalog/approved_catalog.csv"
DEFAULT_OUT_CSV = ROOT_DIR / "data/reports/catalog/component_commercial_coverage.csv"
DEFAULT_OUT_JSON = ROOT_DIR / "data/reports/catalog/component_commercial_coverage_summary.json"
DEFAULT_DEMAND_CSV = ROOT_DIR / "data/reports/catalog/missing_component_demand.csv"

PROBIOTIC_EQUIVALENT_IDS = {
    "COMP_5030A6666E7D",
    "COMP_C5CD8E1D6AAE",
    "COMP_4C01A543D40D",
    "COMP_270BABF303AA",
    "COMP_6CC7081371A8",
    "COMP_BFCFE16644BC",
    "COMP_8BCC1ACBB5A7",
    "COMP_4B39BD01E76F",
    "COMP_6A32E14FD6BE",
    "COMP_43BE32DB2D1B",
    "COMP_27C9BF80AC95",
    "COMP_2F83A2407720",
}

COMPONENT_EQUIVALENT_IDS = {
    # Modelo 2 usa "Cromo" como concepto nutricional; el catálogo puede detectar
    # sales o formas específicas de chromium con otro ID del master.
    "COMP_3F24EA59D864": {"COMP_3F24EA59D864", "COMP_252C51860327"},
    # Modelo 2 puede recomendar "Probióticos" como concepto, mientras el catálogo
    # suele mapear cepas o géneros concretos.
    **{component_id: PROBIOTIC_EQUIVALENT_IDS for component_id in PROBIOTIC_EQUIVALENT_IDS},
}

NON_ORAL_HINTS = (
    "esparadrapo",
    "apósito",
    "aposito",
    "vendaje",
    "parche",
    "crema",
    "cremas",
    "shampoo",
    "champú",
    "gel tópico",
    "gel topico",
    "gel corporal",
    "gel facial",
    "locion",
    "loción",
    "sérum",
    "serum",
    "ampolla",
    "contorno de ojos",
    "tratamiento facial",
    "cuidado facial",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def product_key(row: dict[str, str]) -> str:
    return "|".join(
        [
            row.get("pharmacy", "").strip().lower(),
            row.get("sku", "").strip().lower(),
            row.get("url", "").strip().lower(),
            row.get("commercial_name", "").strip().lower(),
        ]
    )


def is_available(row: dict[str, str]) -> bool:
    return str(row.get("availability") or "").strip().lower() in {"available", "in_stock", "stock"}


def is_probably_oral_supplement(row: dict[str, str]) -> bool:
    text = " ".join(
        [
            row.get("commercial_name", ""),
            row.get("formal_name", ""),
            row.get("component_text", ""),
        ]
    ).lower()
    return not any(hint in text for hint in NON_ORAL_HINTS)


def build_master_index(master_rows: list[dict[str, str]]) -> dict[str, tuple[str, str]]:
    index: dict[str, tuple[str, str]] = {}
    for row in master_rows:
        component_id = (row.get("component_id") or "").strip()
        canonical = (row.get("canonical_name") or "").strip()
        if not component_id or not canonical:
            continue
        index[_normalize_text(canonical)] = (component_id, canonical)
    for component_id, display in COMPONENT_DISPLAY_BY_ID.items():
        index.setdefault(_normalize_text(display), (component_id, display))
    return index


def resolve_component(component_name: str, master_index: dict[str, tuple[str, str]]) -> tuple[str | None, str]:
    key = _normalize_text(component_name)
    if key in COMPONENT_ID_OVERRIDES:
        return COMPONENT_ID_OVERRIDES[key], COMPONENT_DISPLAY_BY_ID.get(COMPONENT_ID_OVERRIDES[key], component_name)
    for candidate in (component_name, *COMPONENT_ALIASES.get(key, ())):
        resolved = master_index.get(_normalize_text(candidate))
        if resolved:
            return resolved
    return None, component_name


def search_terms_for(component_name: str, component_id: str | None) -> list[str]:
    terms: list[str] = []
    if component_name:
        terms.append(component_name)
    if component_id and COMPONENT_DISPLAY_BY_ID.get(component_id):
        terms.append(COMPONENT_DISPLAY_BY_ID[component_id])
    key = _normalize_text(component_name)
    terms.extend(COMPONENT_ALIASES.get(key, ()))

    clean_terms = []
    seen = set()
    for term in terms:
        term = re.sub(r"\s+", " ", str(term).strip())
        normalized = _normalize_text(term)
        if len(normalized) < 2 or normalized in seen:
            continue
        seen.add(normalized)
        clean_terms.append(term)
    return clean_terms[:8]


def status_for(count: int, target: int) -> str:
    if count >= target:
        return "ready"
    if count >= max(1, target - 1):
        return "minimum"
    if count > 0:
        return "weak"
    return "missing"


def equivalent_component_ids(component_id: str) -> set[str]:
    return COMPONENT_EQUIVALENT_IDS.get(component_id, {component_id})


def merge_component_buckets(products_by_component: dict[str, dict[str, Any]], component_id: str) -> dict[str, Any]:
    merged = {
        "products": set(),
        "available_products": set(),
        "safe_products": set(),
        "pharmacies": set(),
        "examples": [],
    }
    seen_examples = set()
    for equivalent_id in equivalent_component_ids(component_id):
        bucket = products_by_component.get(equivalent_id, {})
        merged["products"].update(bucket.get("products", set()))
        merged["available_products"].update(bucket.get("available_products", set()))
        merged["safe_products"].update(bucket.get("safe_products", set()))
        merged["pharmacies"].update(bucket.get("pharmacies", set()))
        for example in bucket.get("examples", []):
            key = "|".join(
                [
                    str(example.get("pharmacy", "")).lower(),
                    str(example.get("commercial_name", "")).lower(),
                    str(example.get("url", "")).lower(),
                ]
            )
            if key in seen_examples:
                continue
            seen_examples.add(key)
            if len(merged["examples"]) < 4:
                merged["examples"].append(example)
    return merged


def audit(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    master_index = build_master_index(read_csv(args.master))
    links = read_csv(args.links)
    catalog = read_csv(args.catalog)

    wanted: dict[str, dict[str, Any]] = {}
    unresolved: list[dict[str, str]] = []
    for row in links:
        component_name = (row.get("component") or "").strip()
        if not component_name:
            continue
        component_id, display_name = resolve_component(component_name, master_index)
        if not component_id:
            unresolved.append(row)
            continue
        item = wanted.setdefault(
            component_id,
            {
                "component_id": component_id,
                "component_name": COMPONENT_DISPLAY_BY_ID.get(component_id, display_name),
                "conditions": set(),
                "roles": set(),
                "evidence": set(),
                "source_components": set(),
            },
        )
        item["conditions"].add(row.get("condition_code", ""))
        item["roles"].add(row.get("recommendation_role", ""))
        item["evidence"].add(row.get("evidence_strength", ""))
        item["source_components"].add(component_name)

    products_by_component: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "products": set(),
            "available_products": set(),
            "safe_products": set(),
            "pharmacies": set(),
            "examples": [],
        }
    )
    for row in catalog:
        component_id = (row.get("component_id") or "").strip()
        if not component_id:
            continue
        bucket = products_by_component[component_id]
        key = product_key(row)
        bucket["products"].add(key)
        if is_available(row):
            bucket["available_products"].add(key)
        if is_available(row) and is_probably_oral_supplement(row):
            bucket["safe_products"].add(key)
            bucket["pharmacies"].add(row.get("pharmacy", "").strip())
            if len(bucket["examples"]) < 4:
                bucket["examples"].append(
                    {
                        "pharmacy": row.get("pharmacy", ""),
                        "commercial_name": row.get("commercial_name", ""),
                        "price": row.get("price", ""),
                        "url": row.get("url", ""),
                    }
                )

    rows: list[dict[str, Any]] = []
    for component_id, item in wanted.items():
        bucket = merge_component_buckets(products_by_component, component_id)
        safe_count = len(bucket.get("safe_products", set()))
        row = {
            "component_id": component_id,
            "component_name": item["component_name"],
            "rotation_status": status_for(safe_count, args.target_products),
            "target_products": args.target_products,
            "distinct_products": len(bucket.get("products", set())),
            "available_products": len(bucket.get("available_products", set())),
            "safe_rotation_products": safe_count,
            "distinct_pharmacies": len(bucket.get("pharmacies", set())),
            "conditions": ";".join(sorted(filter(None, item["conditions"]))),
            "recommendation_roles": ";".join(sorted(filter(None, item["roles"]))),
            "evidence_strengths": ";".join(sorted(filter(None, item["evidence"]))),
            "search_terms": ";".join(search_terms_for(item["component_name"], component_id)),
            "example_products_json": json.dumps(bucket.get("examples", []), ensure_ascii=False),
        }
        rows.append(row)

    rows.sort(key=lambda r: (r["rotation_status"] != "missing", r["safe_rotation_products"], r["component_name"]))
    summary = {
        "components_recommended_by_model2": len(rows),
        "target_products": args.target_products,
        "ready": sum(1 for row in rows if row["rotation_status"] == "ready"),
        "minimum": sum(1 for row in rows if row["rotation_status"] == "minimum"),
        "weak": sum(1 for row in rows if row["rotation_status"] == "weak"),
        "missing": sum(1 for row in rows if row["rotation_status"] == "missing"),
        "unresolved_condition_components": len(unresolved),
        "outputs": {"csv": str(args.out_csv), "json": str(args.out_json)},
    }
    return rows, summary


def demand_reason(row: dict[str, Any]) -> str:
    if int(row.get("safe_rotation_products") or 0) == 0:
        return "sin_producto_comercial_validado"
    if int(row.get("distinct_pharmacies") or 0) < 2:
        return "poca_diversidad_de_farmacias"
    return "cobertura_comercial_debil"


def demand_next_action(row: dict[str, Any]) -> str:
    if row.get("rotation_status") == "missing":
        return "buscar_productos_por_alias_y_validar_rs"
    return "sumar_rotacion_hasta_cumplir_target"


def build_missing_demand(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    demand_rows: list[dict[str, Any]] = []
    for row in rows:
        if row.get("rotation_status") not in {"missing", "weak"}:
            continue
        demand_rows.append(
            {
                "component_id": row.get("component_id", ""),
                "component_name": row.get("component_name", ""),
                "demand_status": row.get("rotation_status", ""),
                "target_products": row.get("target_products", ""),
                "safe_rotation_products": row.get("safe_rotation_products", ""),
                "distinct_pharmacies": row.get("distinct_pharmacies", ""),
                "conditions": row.get("conditions", ""),
                "recommendation_roles": row.get("recommendation_roles", ""),
                "evidence_strengths": row.get("evidence_strengths", ""),
                "search_terms": row.get("search_terms", ""),
                "reason": demand_reason(row),
                "next_action": demand_next_action(row),
            }
        )
    return demand_rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audita cobertura comercial por componente recomendado por Modelo 2.")
    parser.add_argument("--links", type=Path, default=DEFAULT_LINKS)
    parser.add_argument("--master", type=Path, default=DEFAULT_MASTER)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--target-products", type=int, default=4)
    parser.add_argument("--out-csv", type=Path, default=DEFAULT_OUT_CSV)
    parser.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    parser.add_argument("--demand-out-csv", type=Path, default=DEFAULT_DEMAND_CSV)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows, summary = audit(args)
    fieldnames = [
        "component_id",
        "component_name",
        "rotation_status",
        "target_products",
        "distinct_products",
        "available_products",
        "safe_rotation_products",
        "distinct_pharmacies",
        "conditions",
        "recommendation_roles",
        "evidence_strengths",
        "search_terms",
        "example_products_json",
    ]
    write_csv(args.out_csv, rows, fieldnames)
    demand_rows = build_missing_demand(rows)
    write_csv(
        args.demand_out_csv,
        demand_rows,
        [
            "component_id",
            "component_name",
            "demand_status",
            "target_products",
            "safe_rotation_products",
            "distinct_pharmacies",
            "conditions",
            "recommendation_roles",
            "evidence_strengths",
            "search_terms",
            "reason",
            "next_action",
        ],
    )
    summary["outputs"]["demand_csv"] = str(args.demand_out_csv)
    summary["missing_component_demand"] = len(demand_rows)
    write_json(args.out_json, {**summary, "missing_components": [row for row in rows if row["rotation_status"] == "missing"]})
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
