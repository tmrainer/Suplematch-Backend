from __future__ import annotations

import argparse
import csv
import json
import tempfile
from pathlib import Path
from typing import Any

from app.core.config import BASE_DIR
from app.domains.catalog.catalogo_csv import _catalog_by_component
from app.domains.catalog.servicio_catalogo_productos import ProductCatalogService


REPORT_DIR = BASE_DIR / "data" / "reports" / "commercial_engine"


FIELDNAMES = [
    "pharmacy",
    "commercial_name",
    "formal_name",
    "registro_sanitario",
    "digemid_producto",
    "component_id",
    "ingredient",
    "amount",
    "unit",
    "amount_mg",
    "component_match_score",
    "price",
    "currency",
    "availability",
    "url",
    "sku",
    "brand",
    "regulatory_status",
]


def _row(**kwargs: Any) -> dict[str, Any]:
    base = {field: "" for field in FIELDNAMES}
    base.update(
        {
            "currency": "PEN",
            "availability": "available",
            "component_match_score": "100",
            "regulatory_status": "digemid_match",
        }
    )
    base.update(kwargs)
    return base


def _benchmark_rows() -> list[dict[str, Any]]:
    return [
        _row(
            pharmacy="Inkafarma",
            commercial_name="B12 Complejo Multivitaminico",
            formal_name="Complejo B",
            registro_sanitario="DE-B12-MULTI",
            digemid_producto="COMPLEJO B",
            component_id="cmp_b12",
            ingredient="VITAMINA B12",
            amount="1000",
            unit="mcg",
            price="18.0",
            url="https://example.test/b12-multi",
            sku="b12-multi",
            brand="A",
        ),
        _row(
            pharmacy="Inkafarma",
            commercial_name="B12 Complejo Multivitaminico",
            formal_name="Complejo B",
            registro_sanitario="DE-B12-MULTI",
            digemid_producto="COMPLEJO B",
            component_id="cmp_zinc",
            ingredient="ZINC",
            amount="15",
            unit="mg",
            amount_mg="15",
            component_match_score="90",
            price="18.0",
            url="https://example.test/b12-multi",
            sku="b12-multi",
            brand="A",
        ),
        _row(
            pharmacy="Mifarma",
            commercial_name="Vitamina B12 Unitaria",
            formal_name="Vitamina B12",
            registro_sanitario="DE-B12-UNIT",
            digemid_producto="VITAMINA B12",
            component_id="cmp_b12",
            ingredient="VITAMINA B12",
            amount="1000",
            unit="mcg",
            price="26.0",
            url="https://example.test/b12-unit",
            sku="b12-unit",
            brand="B",
        ),
        _row(
            pharmacy="Inkafarma",
            commercial_name="Omega 3 Aceite de Pescado",
            formal_name="Omega 3 marino",
            registro_sanitario="DE-OMEGA-FISH",
            digemid_producto="OMEGA 3 ACEITE DE PESCADO",
            component_id="cmp_omega",
            ingredient="EPA DHA aceite de pescado",
            amount="1000",
            unit="mg",
            amount_mg="1000",
            price="18.0",
            url="https://example.test/omega-fish",
            sku="omega-fish",
            brand="C",
        ),
        _row(
            pharmacy="Boticas Peru",
            commercial_name="Omega 3 de Algas",
            formal_name="Omega 3 vegetal",
            registro_sanitario="DE-OMEGA-ALGAE",
            digemid_producto="OMEGA 3 ALGAS",
            component_id="cmp_omega",
            ingredient="DHA de algas",
            amount="500",
            unit="mg",
            amount_mg="500",
            component_match_score="94",
            price="44.0",
            url="https://example.test/omega-algae",
            sku="omega-algae",
            brand="D",
        ),
        _row(
            pharmacy="Inkafarma",
            commercial_name="Creatina Monohidrato",
            formal_name="Creatina",
            registro_sanitario="DE-CREA",
            digemid_producto="CREATINA",
            component_id="cmp_creatine",
            ingredient="Creatina monohidrato",
            amount="3",
            unit="g",
            amount_mg="3000",
            price="60.0",
            url="https://example.test/creatine",
            sku="creatine",
            brand="E",
        ),
        _row(
            pharmacy="Inkafarma",
            commercial_name="Vitamina D Economica",
            formal_name="Vitamina D",
            registro_sanitario="DE-D-CHEAP",
            digemid_producto="VITAMINA D",
            component_id="cmp_vit_d",
            ingredient="VITAMINA D3",
            amount="1000",
            unit="UI",
            component_match_score="96",
            price="18.0",
            url="https://example.test/vitd-cheap",
            sku="vitd-cheap",
            brand="F",
        ),
        _row(
            pharmacy="Mifarma",
            commercial_name="Vitamina D Premium",
            formal_name="Vitamina D",
            registro_sanitario="DE-D-PREMIUM",
            digemid_producto="VITAMINA D",
            component_id="cmp_vit_d",
            ingredient="VITAMINA D3",
            amount="1000",
            unit="UI",
            price="80.0",
            url="https://example.test/vitd-premium",
            sku="vitd-premium",
            brand="G",
        ),
        _row(
            pharmacy="Boticas Peru",
            commercial_name="Calcio",
            formal_name="Calcio",
            registro_sanitario="DE-CA",
            digemid_producto="CALCIO",
            component_id="cmp_calcium",
            ingredient="Calcio",
            amount="500",
            unit="mg",
            amount_mg="500",
            price="22.0",
            url="https://example.test/calcium",
            sku="calcium",
            brand="H",
        ),
    ]


def _write_catalog(path: Path) -> None:
    rows = _benchmark_rows()
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def _case_result(case_id: str, passed: bool, details: dict[str, Any]) -> dict[str, Any]:
    return {"case_id": case_id, "passed": passed, **details}


def evaluate_catalog(catalog_path: Path) -> list[dict[str, Any]]:
    _catalog_by_component.cache_clear()
    cases: list[dict[str, Any]] = []

    b12_products = ProductCatalogService(catalog_path=catalog_path).products_for_component("cmp_b12", limit=2)
    cases.append(
        _case_result(
            "unit_product_preference",
            bool(b12_products and b12_products[0].get("component_match_type") == "unit_component"),
            {
                "selected": b12_products[0].get("commercial_name") if b12_products else "",
                "commercial_score": b12_products[0].get("commercial_score") if b12_products else None,
            },
        )
    )

    omega_products = ProductCatalogService(
        catalog_path=catalog_path,
        restrictions=["alergia_pescado_mariscos"],
    ).products_for_component("cmp_omega", limit=2)
    cases.append(
        _case_result(
            "fish_allergy_blocks_marine_omega",
            bool(omega_products and all("pescado" not in product.get("commercial_name", "").lower() for product in omega_products)),
            {"selected": "|".join(product.get("commercial_name", "") for product in omega_products)},
        )
    )

    creatine_products = ProductCatalogService(
        catalog_path=catalog_path,
        safety_conditions=["enfermedad_renal"],
    ).products_for_component("cmp_creatine", limit=1)
    cases.append(
        _case_result(
            "renal_safety_blocks_creatine_product",
            len(creatine_products) == 0,
            {"selected_count": len(creatine_products)},
        )
    )

    vitd_products = ProductCatalogService(catalog_path=catalog_path, budget_max=25).products_for_component("cmp_vit_d", limit=2)
    cases.append(
        _case_result(
            "budget_low_prioritizes_affordable_product",
            bool(vitd_products and vitd_products[0].get("sku") == "vitd-cheap"),
            {
                "selected": vitd_products[0].get("commercial_name") if vitd_products else "",
                "price_score": vitd_products[0].get("price_score") if vitd_products else None,
            },
        )
    )

    pack_products = ProductCatalogService(catalog_path=catalog_path).select_products_for_pack(["cmp_vit_d", "cmp_calcium"])
    pharmacies = {product.get("pharmacy") for product in pack_products}
    cases.append(
        _case_result(
            "pack_selection_preserves_pharmacy_diversity",
            len(pack_products) == 2 and len(pharmacies) == 2,
            {"selected_pharmacies": "|".join(sorted(str(value) for value in pharmacies if value))},
        )
    )

    auditable = b12_products[0] if b12_products else {}
    cases.append(
        _case_result(
            "commercial_score_is_auditable",
            bool(
                auditable.get("commercial_score_breakdown")
                and auditable.get("commercial_quality_flags")
                and auditable.get("selection_reasons")
            ),
            {
                "has_breakdown": bool(auditable.get("commercial_score_breakdown")),
                "has_flags": bool(auditable.get("commercial_quality_flags")),
                "reason_count": len(auditable.get("selection_reasons") or []),
            },
        )
    )

    return cases


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evalúa el motor comercial con casos fijos de catálogo.")
    parser.add_argument("--details-out", type=Path, default=REPORT_DIR / "01_commercial_engine_case_details.csv")
    parser.add_argument("--summary-out", type=Path, default=REPORT_DIR / "01_commercial_engine_summary.json")
    parser.add_argument("--min-pass-rate", type=float, default=1.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    with tempfile.TemporaryDirectory(prefix="suplematch-commercial-") as tmp:
        catalog_path = Path(tmp) / "approved_catalog.csv"
        _write_catalog(catalog_path)
        details = evaluate_catalog(catalog_path)

    passed = sum(1 for row in details if row["passed"])
    pass_rate = passed / max(len(details), 1)
    errors = []
    if pass_rate < args.min_pass_rate:
        errors.append(f"pass_rate_below_threshold={pass_rate:.4f}<{args.min_pass_rate}")

    summary = {
        "status": "failed" if errors else "passed",
        "errors": errors,
        "cases": len(details),
        "passed": passed,
        "pass_rate": round(pass_rate, 4),
        "details_path": str(args.details_out),
        "summary_path": str(args.summary_out),
    }

    write_csv(args.details_out, details)
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
