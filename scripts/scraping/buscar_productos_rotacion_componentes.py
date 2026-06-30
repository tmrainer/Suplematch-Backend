from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from scripts.catalog.auditar_cobertura_componentes import (  # noqa: E402
    DEFAULT_OUT_CSV as DEFAULT_COVERAGE_CSV,
    equivalent_component_ids,
    is_available,
    is_probably_oral_supplement,
    product_key,
    read_csv,
    write_csv,
    write_json,
)
from app.ml.runtime.modelo2_inference import _normalize_text  # noqa: E402


DEFAULT_RAW_OUT = ROOT_DIR / "data/reports/scraping/rotation_candidates_raw.csv"
DEFAULT_REJECTS_OUT = ROOT_DIR / "data/reports/scraping/rotation_candidates_rejected.csv"
DEFAULT_BY_COMPONENT_OUT = ROOT_DIR / "data/reports/scraping/rotation_candidates_by_component.csv"
DEFAULT_RELATIONS_OUT = ROOT_DIR / "data/reports/scraping/rotation_candidate_relations.csv"
DEFAULT_SUMMARY_OUT = ROOT_DIR / "data/reports/scraping/rotation_candidates_summary.json"


def split_terms(value: str) -> list[str]:
    terms = []
    seen = set()
    for raw in str(value or "").split(";"):
        term = " ".join(raw.strip().split())
        key = term.lower()
        if len(term) < 2 or key in seen:
            continue
        seen.add(key)
        terms.append(term)
    return terms


def select_components(args: argparse.Namespace) -> list[dict[str, str]]:
    rows = read_csv(args.coverage_csv)
    allowed_statuses = set(args.status)
    selected = [
        row for row in rows
        if row.get("rotation_status") in allowed_statuses
        and int(float(row.get("safe_rotation_products") or 0)) < args.target_products
    ]
    if args.component:
        wanted = {item.strip() for item in args.component if item.strip()}
        selected = [row for row in rows if row.get("component_id") in wanted or row.get("component_name") in wanted]
    return selected[: args.max_components]


def run_scraper(args: argparse.Namespace, components: list[dict[str, str]]) -> int:
    terms: list[str] = []
    seen = set()
    for row in components:
        for term in split_terms(row.get("search_terms", "")):
            key = term.lower()
            if key in seen:
                continue
            seen.add(key)
            terms.append(term)
    if not terms:
        raise SystemExit("No hay términos para buscar. Ejecuta primero auditar_cobertura_componentes.py.")

    command = [
        sys.executable,
        "scripts/scraping/scraper_suplementos.py",
        "--out",
        str(args.raw_out),
        "--rejects-out",
        str(args.rejects_out),
        "--limit-per-pharmacy",
        str(args.limit_per_pharmacy),
        "--delay",
        str(args.delay),
        "--infer-registro",
    ]
    if args.allow_unverified:
        command.append("--allow-unverified")
    if args.fetch_detail_pages:
        command.append("--fetch-detail-pages")
    if args.ocr_product_images:
        command.append("--ocr-product-images")
    for pharmacy in args.pharmacy:
        command.extend(["--pharmacy", pharmacy])
    for term in terms[: args.max_terms]:
        command.extend(["--term", term])

    print(json.dumps({"running": command, "terms": terms[: args.max_terms]}, ensure_ascii=False, indent=2))
    process = subprocess.run(command, cwd=ROOT_DIR, check=False)
    return process.returncode


def candidate_component_ids(row: dict[str, str]) -> set[str]:
    ids = set()
    if row.get("component_id"):
        ids.add(row["component_id"].strip())
    for value in str(row.get("component_ids_detected") or "").split(";"):
        value = value.strip()
        if value:
            ids.add(value)
    return ids


def candidate_text(row: dict[str, str]) -> str:
    return _normalize_text(
        " ".join(
            [
                row.get("commercial_name", ""),
                row.get("formal_name", ""),
                row.get("component_text", ""),
                row.get("component_names_detected", ""),
            ]
        )
    )


def text_mentions_component(row: dict[str, str], component_row: dict[str, str]) -> bool:
    text = candidate_text(row)
    if not text:
        return False
    for term in split_terms(component_row.get("search_terms", "")):
        normalized = _normalize_text(term)
        if len(normalized) >= 4 and normalized in text:
            return True
    return False


def summarize_candidates(args: argparse.Namespace, components: list[dict[str, str]]) -> dict[str, Any]:
    wanted = {row["component_id"]: row for row in components}
    raw_rows = read_csv(args.raw_out)
    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {"keys": set(), "pharmacies": set(), "examples": []})
    relation_rows: list[dict[str, Any]] = []

    for row in raw_rows:
        if not is_available(row) or not is_probably_oral_supplement(row):
            continue
        ids = candidate_component_ids(row)
        for component_id, component_row in wanted.items():
            equivalent_ids = equivalent_component_ids(component_id)
            matched_ids = sorted(ids.intersection(equivalent_ids))
            matched_by_text = text_mentions_component(row, component_row)
            if not matched_ids and not matched_by_text:
                continue
            bucket = grouped[component_id]
            key = product_key(row)
            if key in bucket["keys"]:
                continue
            bucket["keys"].add(key)
            bucket["pharmacies"].add(row.get("pharmacy", ""))
            relation_rows.append({
                "component_id": component_id,
                "component_name": component_row.get("component_name", ""),
                "pharmacy": row.get("pharmacy", ""),
                "commercial_name": row.get("commercial_name", ""),
                "price": row.get("price", ""),
                "availability": row.get("availability", ""),
                "registro_sanitario": row.get("registro_sanitario", ""),
                "url": row.get("url", ""),
                "sku": row.get("sku", ""),
                "component_traceable": row.get("component_traceable", ""),
                "component_ids_detected": row.get("component_ids_detected", ""),
                "component_names_detected": row.get("component_names_detected", ""),
                "match_basis": ";".join(matched_ids) if matched_ids else "alias_text",
                "needs_catalog_review": "yes",
            })
            if len(bucket["examples"]) < args.target_products:
                bucket["examples"].append({
                    "pharmacy": row.get("pharmacy", ""),
                    "commercial_name": row.get("commercial_name", ""),
                    "price": row.get("price", ""),
                    "availability": row.get("availability", ""),
                    "registro_sanitario": row.get("registro_sanitario", ""),
                    "url": row.get("url", ""),
                    "component_traceable": row.get("component_traceable", ""),
                })

    output_rows: list[dict[str, Any]] = []
    for component_id, row in wanted.items():
        bucket = grouped.get(component_id, {"keys": set(), "pharmacies": set(), "examples": []})
        candidate_count = len(bucket["keys"])
        previous_count = int(float(row.get("safe_rotation_products") or 0))
        combined = previous_count + candidate_count
        output_rows.append({
            "component_id": component_id,
            "component_name": row.get("component_name", ""),
            "previous_safe_products": previous_count,
            "new_candidate_products": candidate_count,
            "combined_possible_products": combined,
            "target_products": args.target_products,
            "candidate_pharmacies": len(bucket["pharmacies"]),
            "status_after_candidates": "ready" if combined >= args.target_products else "needs_more",
            "search_terms": row.get("search_terms", ""),
            "examples_json": json.dumps(bucket["examples"], ensure_ascii=False),
        })

    output_rows.sort(key=lambda r: (r["status_after_candidates"] != "needs_more", -r["new_candidate_products"], r["component_name"]))
    fieldnames = [
        "component_id",
        "component_name",
        "previous_safe_products",
        "new_candidate_products",
        "combined_possible_products",
        "target_products",
        "candidate_pharmacies",
        "status_after_candidates",
        "search_terms",
        "examples_json",
    ]
    write_csv(args.by_component_out, output_rows, fieldnames)
    relation_fieldnames = [
        "component_id",
        "component_name",
        "pharmacy",
        "commercial_name",
        "price",
        "availability",
        "registro_sanitario",
        "url",
        "sku",
        "component_traceable",
        "component_ids_detected",
        "component_names_detected",
        "match_basis",
        "needs_catalog_review",
    ]
    write_csv(args.relations_out, relation_rows, relation_fieldnames)
    summary = {
        "components_targeted": len(components),
        "raw_candidates": len(raw_rows),
        "component_product_relations": len(relation_rows),
        "components_ready_after_candidates": sum(1 for row in output_rows if row["status_after_candidates"] == "ready"),
        "components_still_needing_more": sum(1 for row in output_rows if row["status_after_candidates"] == "needs_more"),
        "outputs": {
            "raw": str(args.raw_out),
            "rejects": str(args.rejects_out),
            "by_component": str(args.by_component_out),
            "relations": str(args.relations_out),
            "summary": str(args.summary_out),
        },
    }
    write_json(args.summary_out, {**summary, "components": output_rows})
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Busca candidatos comerciales para rotación por componente.")
    parser.add_argument("--coverage-csv", type=Path, default=DEFAULT_COVERAGE_CSV)
    parser.add_argument("--raw-out", type=Path, default=DEFAULT_RAW_OUT)
    parser.add_argument("--rejects-out", type=Path, default=DEFAULT_REJECTS_OUT)
    parser.add_argument("--by-component-out", type=Path, default=DEFAULT_BY_COMPONENT_OUT)
    parser.add_argument("--relations-out", type=Path, default=DEFAULT_RELATIONS_OUT)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY_OUT)
    parser.add_argument("--target-products", type=int, default=4)
    parser.add_argument("--max-components", type=int, default=12)
    parser.add_argument("--max-terms", type=int, default=60)
    parser.add_argument("--limit-per-pharmacy", type=int, default=80)
    parser.add_argument("--delay", type=float, default=0.2)
    parser.add_argument("--status", action="append", default=["missing", "weak"], choices=["missing", "weak", "minimum", "ready"])
    parser.add_argument("--component", action="append", default=[], help="component_id o nombre exacto. Puede repetirse.")
    parser.add_argument("--pharmacy", action="append", default=[], choices=["inkafarma", "mifarma", "boticasperu", "farmaciauniversal", "hogarysalud", "boticasysalud"])
    parser.add_argument("--allow-unverified", action="store_true")
    parser.add_argument("--fetch-detail-pages", action="store_true", help="Busca RS y composición en página/API de detalle.")
    parser.add_argument("--ocr-product-images", action="store_true", help="Usa OCR de imagen de producto para recuperar RS como fallback.")
    parser.add_argument("--skip-scrape", action="store_true", help="Solo resume el CSV raw existente.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    components = select_components(args)
    if not components:
        raise SystemExit("No hay componentes objetivo con los filtros indicados.")
    if not args.skip_scrape:
        rc = run_scraper(args, components)
        if rc != 0:
            return rc
    summarize_candidates(args, components)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
