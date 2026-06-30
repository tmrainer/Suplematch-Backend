from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from app.db.models import CommercialProduct, Pharmacy
from app.db.session import SessionLocal


def clean(value: Any) -> str:
    return str(value or "").strip()


def parse_float(value: Any) -> float | None:
    try:
        return float(str(value or "").strip())
    except ValueError:
        return None


def key_from_parts(pharmacy: str, sku: str, url: str) -> tuple[str, str]:
    return (clean(pharmacy).lower(), clean(sku or url).lower())


def read_catalog(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows: dict[tuple[str, str], dict[str, str]] = {}
        for row in reader:
            key = key_from_parts(row.get("pharmacy", ""), row.get("sku", ""), row.get("url", ""))
            if key[0] and key[1]:
                rows[key] = row
        return rows


def summarize_rejects(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {"rows": 0, "by_reason": {}}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    reasons = Counter(clean(row.get("reason")) or "unknown" for row in rows)
    return {"rows": len(rows), "by_reason": dict(reasons.most_common(20))}


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera diff entre catálogo CSV aprobado y PostgreSQL.")
    parser.add_argument("--catalog", type=Path, default=Path("data/catalog/approved_catalog.csv"))
    parser.add_argument("--rejects", type=Path, default=Path("data/reports/scraping/supplements_rejected.csv"))
    parser.add_argument("--out", type=Path, default=Path("data/reports/scraping/catalog_diff_current.json"))
    parser.add_argument("--price-change-threshold", type=float, default=0.01)
    args = parser.parse_args()

    csv_rows = read_catalog(args.catalog)
    with SessionLocal() as db:
        db_rows: dict[tuple[str, str], CommercialProduct] = {}
        for product, pharmacy in db.execute(select(CommercialProduct, Pharmacy).join(Pharmacy)):
            key = key_from_parts(pharmacy.name, product.sku or "", product.url or "")
            if key[0] and key[1]:
                db_rows[key] = product

    csv_keys = set(csv_rows)
    db_keys = set(db_rows)
    new_keys = sorted(csv_keys - db_keys)
    removed_keys = sorted(db_keys - csv_keys)
    common_keys = sorted(csv_keys & db_keys)
    price_changes = []
    availability_changes = []

    for key in common_keys:
        row = csv_rows[key]
        product = db_rows[key]
        new_price = parse_float(row.get("price"))
        old_price = product.price
        if old_price is not None and new_price is not None:
            diff = new_price - old_price
            pct = diff / old_price if old_price else 0
            if abs(pct) >= args.price_change_threshold:
                price_changes.append(
                    {
                        "pharmacy": row.get("pharmacy"),
                        "sku": row.get("sku"),
                        "commercial_name": row.get("commercial_name"),
                        "old_price": old_price,
                        "new_price": new_price,
                        "delta": round(diff, 4),
                        "delta_pct": round(pct, 4),
                    }
                )
        new_availability = clean(row.get("availability")).lower()
        old_availability = clean(product.availability).lower()
        if new_availability and old_availability and new_availability != old_availability:
            availability_changes.append(
                {
                    "pharmacy": row.get("pharmacy"),
                    "sku": row.get("sku"),
                    "commercial_name": row.get("commercial_name"),
                    "old_availability": old_availability,
                    "new_availability": new_availability,
                }
            )

    by_pharmacy = Counter(row.get("pharmacy") or "unknown" for row in csv_rows.values())
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "catalog_path": str(args.catalog),
        "status": "generated",
        "summary": {
            "csv_products": len(csv_rows),
            "db_products": len(db_rows),
            "new_products": len(new_keys),
            "removed_products": len(removed_keys),
            "price_changes": len(price_changes),
            "availability_changes": len(availability_changes),
            "pharmacies": dict(sorted(by_pharmacy.items())),
        },
        "samples": {
            "new_products": [
                {
                    "pharmacy": csv_rows[key].get("pharmacy"),
                    "sku": csv_rows[key].get("sku"),
                    "commercial_name": csv_rows[key].get("commercial_name"),
                    "price": parse_float(csv_rows[key].get("price")),
                    "availability": csv_rows[key].get("availability"),
                }
                for key in new_keys[:50]
            ],
            "removed_products": [
                {
                    "pharmacy": key[0],
                    "sku": db_rows[key].sku,
                    "commercial_name": db_rows[key].commercial_name,
                    "price": db_rows[key].price,
                    "availability": db_rows[key].availability,
                }
                for key in removed_keys[:50]
            ],
            "price_changes": sorted(price_changes, key=lambda item: abs(item["delta_pct"]), reverse=True)[:50],
            "availability_changes": availability_changes[:50],
        },
        "rejects": summarize_rejects(args.rejects),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
