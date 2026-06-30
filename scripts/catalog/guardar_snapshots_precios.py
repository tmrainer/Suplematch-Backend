from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from app.db.models import CommercialProduct, Pharmacy, ProductPriceSnapshot
from app.db.session import SessionLocal


def clean(value: Any) -> str:
    return str(value or "").strip()


def parse_float(value: Any) -> float | None:
    try:
        return float(str(value or "").strip())
    except ValueError:
        return None


def parse_int(value: Any) -> int | None:
    try:
        return int(float(str(value or "").strip()))
    except ValueError:
        return None


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def key(pharmacy: str, sku: str, url: str) -> tuple[str, str]:
    return (clean(pharmacy).lower(), clean(sku or url).lower())


def main() -> int:
    parser = argparse.ArgumentParser(description="Guarda snapshots de precio/stock desde catálogo aprobado.")
    parser.add_argument("--catalog", type=Path, default=Path("data/catalog/approved_catalog.csv"))
    parser.add_argument("--catalog-job-id", default="")
    args = parser.parse_args()

    job_id = UUID(args.catalog_job_id) if args.catalog_job_id else None
    rows = read_rows(args.catalog)
    with SessionLocal() as db:
        products = {
            key(pharmacy.name, product.sku or "", product.url or ""): product
            for product, pharmacy in db.execute(select(CommercialProduct, Pharmacy).join(Pharmacy))
        }
        inserted = 0
        for row in rows:
            row_key = key(row.get("pharmacy", ""), row.get("sku", ""), row.get("url", ""))
            product = products.get(row_key)
            db.add(
                ProductPriceSnapshot(
                    product_id=product.id if product is not None else None,
                    catalog_job_id=job_id,
                    pharmacy=clean(row.get("pharmacy")) or "unknown",
                    sku=clean(row.get("sku")) or None,
                    url=clean(row.get("url")) or None,
                    commercial_name=clean(row.get("commercial_name")) or None,
                    price=parse_float(row.get("price")),
                    currency=clean(row.get("currency")) or None,
                    availability=clean(row.get("availability")) or None,
                    stock=parse_int(row.get("stock")),
                    registro_sanitario=clean(row.get("registro_sanitario")) or None,
                    raw_payload_json=dict(row),
                )
            )
            inserted += 1
            if inserted % 500 == 0:
                db.commit()
        db.commit()

    print(f"price_snapshots=ok inserted={inserted} catalog={args.catalog}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
