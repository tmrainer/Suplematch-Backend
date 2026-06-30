from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

@dataclass(frozen=True)
class CatalogProduct:
    pharmacy: str
    commercial_name: str
    formal_name: str | None
    registro_sanitario: str
    digemid_producto: str | None
    component_id: str
    ingredient: str
    amount: str | None
    unit: str | None
    amount_mg: float | None
    component_match_score: float | None
    price: float
    currency: str
    availability: str
    url: str
    sku: str | None
    brand: str | None
    regulatory_status: str
    image_url: str | None = None
    image_source: str | None = None
    image_local_path: str | None = None
    commercial_confidence_score: float | None = None
    commercial_confidence_level: str | None = None
    commercial_confidence_reasons: str | None = None

    @property
    def product_key(self) -> str:
        return f"{self.pharmacy}|{self.sku or self.url}|{self.registro_sanitario}"

    def to_response(self) -> dict[str, Any]:
        return {
            "pharmacy": self.pharmacy,
            "commercial_name": self.commercial_name,
            "formal_name": self.formal_name,
            "registro_sanitario": self.registro_sanitario,
            "digemid_producto": self.digemid_producto,
            "component_id": self.component_id,
            "ingredient": self.ingredient,
            "amount": self.amount,
            "unit": self.unit,
            "amount_mg": self.amount_mg,
            "component_match_score": self.component_match_score,
            "price": self.price,
            "currency": self.currency,
            "availability": self.availability,
            "url": self.url,
            "sku": self.sku,
            "brand": self.brand,
            "image_url": self.image_url,
            "image_source": self.image_source,
            "image_local_path": self.image_local_path,
            "regulatory_status": self.regulatory_status,
            "commercial_confidence_score": self.commercial_confidence_score,
            "commercial_confidence_level": self.commercial_confidence_level,
            "commercial_confidence_reasons": self.commercial_confidence_reasons,
        }


def _clean(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _float(value: Any) -> float | None:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None

    if not math.isfinite(number):
        return None

    return number


def _load_rows(path: Path) -> list[CatalogProduct]:
    if not path.exists():
        return []

    products = []

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)

        for row in reader:
            price = _float(row.get("price"))
            if price is None:
                continue

            if (row.get("availability") or "").strip().lower() != "available":
                continue

            component_id = _clean(row.get("component_id"))
            registro_sanitario = _clean(row.get("registro_sanitario"))
            commercial_name = _clean(row.get("commercial_name"))
            pharmacy = _clean(row.get("pharmacy"))
            url = _clean(row.get("url"))

            if not all([component_id, registro_sanitario, commercial_name, pharmacy, url]):
                continue

            products.append(
                CatalogProduct(
                    pharmacy=pharmacy or "",
                    commercial_name=commercial_name or "",
                    formal_name=_clean(row.get("formal_name")),
                    registro_sanitario=registro_sanitario or "",
                    digemid_producto=_clean(row.get("digemid_producto")),
                    component_id=component_id or "",
                    ingredient=_clean(row.get("ingredient")) or component_id or "",
                    amount=_clean(row.get("amount")),
                    unit=_clean(row.get("unit")),
                    amount_mg=_float(row.get("amount_mg")),
                    component_match_score=_float(row.get("component_match_score")),
                    price=price,
                    currency=_clean(row.get("currency")) or "PEN",
                    availability=_clean(row.get("availability")) or "available",
                    url=url or "",
                    sku=_clean(row.get("sku")),
                    brand=_clean(row.get("brand")),
                    image_url=_clean(row.get("image_url")),
                    image_source=_clean(row.get("image_source")),
                    image_local_path=_clean(row.get("image_local_path")),
                    regulatory_status=_clean(row.get("regulatory_status")) or "digemid_match",
                    commercial_confidence_score=_float(row.get("commercial_confidence_score")),
                    commercial_confidence_level=_clean(row.get("commercial_confidence_level")),
                    commercial_confidence_reasons=_clean(row.get("commercial_confidence_reasons")),
                )
            )

    return products


@lru_cache(maxsize=4)
def _catalog_by_component(path_value: str) -> dict[str, list[CatalogProduct]]:
    products = _load_rows(Path(path_value))
    grouped: dict[str, dict[str, CatalogProduct]] = {}

    for product in products:
        component_group = grouped.setdefault(product.component_id, {})
        existing = component_group.get(product.product_key)

        if existing is None or product.price < existing.price:
            component_group[product.product_key] = product

    return {
        component_id: sorted(items.values(), key=_base_product_sort_key)
        for component_id, items in grouped.items()
    }


def _base_product_sort_key(product: CatalogProduct) -> tuple[float, float, str, str]:
    match_score = product.component_match_score if product.component_match_score is not None else 0.0
    return (
        product.price,
        -match_score,
        product.pharmacy.lower(),
        product.commercial_name.lower(),
    )
