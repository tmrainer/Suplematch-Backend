from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.core.config import settings
from app.db.models import (
    CatalogImportError,
    CatalogImportRun,
    CommercialProduct,
    CommercialProductComponent,
    Component,
    Pharmacy,
    utcnow,
)
from app.db.session import SessionLocal


def clean(value: Any) -> str:
    return str(value or "").strip()


def parse_float(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def parse_int(value: Any) -> int | None:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def slugify(value: str) -> str:
    text = clean(value).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "unknown"


def base_url_from_product_url(url: str) -> str | None:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


class CatalogImporter:
    def __init__(self, catalog_path: Path):
        self.catalog_path = catalog_path

    def run(self) -> dict[str, int]:
        rows = read_rows(self.catalog_path)
        stats = {
            "rows": len(rows),
            "products": 0,
            "components": 0,
            "links": 0,
            "errors": 0,
        }

        with SessionLocal() as db:
            import_run = CatalogImportRun(
                source=str(self.catalog_path),
                status="running",
                total_scraped=len(rows),
            )
            db.add(import_run)
            db.commit()

            pharmacy_cache: dict[str, Pharmacy] = {}
            component_cache: dict[str, Component] = {}
            product_cache: dict[tuple[str, str], CommercialProduct] = {}

            for row in rows:
                try:
                    pharmacy = self._get_pharmacy(db, row, pharmacy_cache)
                    component = self._get_component(db, row, component_cache)
                    product = self._get_product(db, row, pharmacy, product_cache)
                    self._link_product_component(db, row, product, component)
                    stats["products"] += 1
                    stats["links"] += 1
                except Exception as exc:
                    stats["errors"] += 1
                    db.add(
                        CatalogImportError(
                            import_run_id=import_run.id,
                            pharmacy=clean(row.get("pharmacy")) or None,
                            sku=clean(row.get("sku")) or None,
                            url=clean(row.get("url")) or None,
                            reason=str(exc),
                            raw_payload_json=dict(row),
                        )
                    )

                if (stats["products"] + stats["errors"]) % 500 == 0:
                    db.commit()

            import_run.status = "completed" if stats["errors"] == 0 else "completed_with_errors"
            import_run.finished_at = utcnow()
            import_run.total_accepted = stats["products"]
            import_run.total_rejected = stats["errors"]
            db.commit()

        stats["components"] = len(component_cache)
        return stats

    def _get_pharmacy(
        self,
        db,
        row: dict[str, str],
        cache: dict[str, Pharmacy],
    ) -> Pharmacy:
        name = clean(row.get("pharmacy"))
        if not name:
            raise ValueError("pharmacy vacio")

        slug = slugify(name)
        if slug in cache:
            return cache[slug]

        pharmacy = db.scalar(select(Pharmacy).where(Pharmacy.slug == slug))
        if pharmacy is None:
            pharmacy = Pharmacy(
                name=name,
                slug=slug,
                base_url=base_url_from_product_url(clean(row.get("url"))),
                active=True,
            )
            db.add(pharmacy)
            db.flush()
        elif not pharmacy.base_url:
            pharmacy.base_url = base_url_from_product_url(clean(row.get("url")))

        cache[slug] = pharmacy
        return pharmacy

    def _get_component(
        self,
        db,
        row: dict[str, str],
        cache: dict[str, Component],
    ) -> Component:
        component_id = clean(row.get("component_id"))
        if not component_id:
            raise ValueError("component_id vacio")

        if component_id in cache:
            return cache[component_id]

        component = db.scalar(select(Component).where(Component.component_id == component_id))
        if component is None:
            component = Component(
                component_id=component_id,
                canonical_name=clean(row.get("ingredient")) or component_id,
                metadata_json={},
            )
            db.add(component)
            db.flush()
        elif clean(row.get("ingredient")) and component.canonical_name == component.component_id:
            component.canonical_name = clean(row.get("ingredient"))

        cache[component_id] = component
        return component

    def _get_product(
        self,
        db,
        row: dict[str, str],
        pharmacy: Pharmacy,
        cache: dict[tuple[str, str], CommercialProduct],
    ) -> CommercialProduct:
        sku = clean(row.get("sku")) or clean(row.get("url"))
        if not sku:
            raise ValueError("sku/url vacio")

        cache_key = (str(pharmacy.id), sku)
        if cache_key in cache:
            product = cache[cache_key]
            self._update_product(product, row)
            return product

        product = db.scalar(
            select(CommercialProduct).where(
                CommercialProduct.pharmacy_id == pharmacy.id,
                CommercialProduct.sku == sku,
            )
        )
        if product is None:
            product = CommercialProduct(
                pharmacy_id=pharmacy.id,
                sku=sku,
                commercial_name=clean(row.get("commercial_name")),
                formal_name=clean(row.get("formal_name")) or None,
                brand=clean(row.get("brand")) or None,
                url=clean(row.get("url")),
                registro_sanitario=clean(row.get("registro_sanitario")) or None,
                price=parse_float(row.get("price")),
                currency=clean(row.get("currency")) or "PEN",
                availability=clean(row.get("availability")) or "unknown",
                stock=parse_int(row.get("stock")),
                source_strategy=clean(row.get("source_strategy")) or None,
                component_traceable=clean(row.get("regulatory_status")) or "digemid_match",
                commercial_status="active",
                last_seen_at=utcnow(),
                raw_payload_json=dict(row),
            )
            db.add(product)
            db.flush()
        else:
            self._update_product(product, row)

        cache[cache_key] = product
        return product

    def _update_product(self, product: CommercialProduct, row: dict[str, str]) -> None:
        product.commercial_name = clean(row.get("commercial_name")) or product.commercial_name
        product.formal_name = clean(row.get("formal_name")) or product.formal_name
        product.brand = clean(row.get("brand")) or product.brand
        product.url = clean(row.get("url")) or product.url
        product.registro_sanitario = clean(row.get("registro_sanitario")) or product.registro_sanitario
        product.price = parse_float(row.get("price"))
        product.currency = clean(row.get("currency")) or product.currency
        product.availability = clean(row.get("availability")) or product.availability
        product.stock = parse_int(row.get("stock"))
        product.source_strategy = clean(row.get("source_strategy")) or product.source_strategy
        product.last_seen_at = utcnow()
        product.raw_payload_json = dict(row)

    def _link_product_component(
        self,
        db,
        row: dict[str, str],
        product: CommercialProduct,
        component: Component,
    ) -> None:
        ingredient = clean(row.get("ingredient")) or None
        existing = db.scalar(
            select(CommercialProductComponent).where(
                CommercialProductComponent.product_id == product.id,
                CommercialProductComponent.component_id == component.id,
                CommercialProductComponent.ingredient == ingredient,
            )
        )
        if existing is not None:
            existing.amount = clean(row.get("amount")) or None
            existing.unit = clean(row.get("unit")) or None
            existing.amount_mg = parse_float(row.get("amount_mg"))
            existing.match_score = parse_float(row.get("component_match_score"))
            existing.match_method = clean(row.get("component_match_method")) or None
            return

        db.add(
            CommercialProductComponent(
                product_id=product.id,
                component_id=component.id,
                ingredient=ingredient,
                amount=clean(row.get("amount")) or None,
                unit=clean(row.get("unit")) or None,
                amount_mg=parse_float(row.get("amount_mg")),
                match_score=parse_float(row.get("component_match_score")),
                match_method=clean(row.get("component_match_method")) or None,
                source="approved_catalog_csv",
            )
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Importa approved_catalog.csv a PostgreSQL.")
    parser.add_argument("--catalog", type=Path, default=settings.APPROVED_CATALOG_PATH)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    stats = CatalogImporter(args.catalog).run()
    print(f"rows={stats['rows']}")
    print(f"products_seen={stats['products']}")
    print(f"components_seen={stats['components']}")
    print(f"links_seen={stats['links']}")
    print(f"errors={stats['errors']}")
    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
