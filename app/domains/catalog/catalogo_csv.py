from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.domains.catalog.seguridad_productos import verified_restriction_flags


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
    # Composición oficial de la fila y flags verificados por el enriquecimiento
    # (`contains_*`, `*_verified`, `label_status`), ver docs/catalog_quality_enrichment.md.
    digemid_composicion: str | None = None
    restriction_flags_verified: tuple[str, ...] = ()
    label_status: str | None = None
    label_verified_at: str | None = None
    label_verification_source: str | None = None

    @property
    def product_key(self) -> str:
        return f"{self.pharmacy}|{self.sku or self.url}|{self.registro_sanitario}"

    @property
    def composition_key(self) -> tuple[str, str]:
        """Identifica el producto comercial (farmacia + sku/url) sin importar el componente."""
        return composition_key(self.pharmacy, self.sku, self.url)

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
            "digemid_composicion": self.digemid_composicion,
            "restriction_flags_verified": list(self.restriction_flags_verified),
            "label_status": self.label_status,
            "label_verified_at": self.label_verified_at,
            "label_verification_source": self.label_verification_source,
        }


@dataclass(frozen=True)
class ProductComposition:
    """Composición completa de un producto comercial: unión de todas sus filas del CSV."""

    ingredients: tuple[str, ...]
    component_ids: tuple[str, ...]
    digemid_composicion: str
    restriction_flags_verified: tuple[str, ...]


def composition_key(pharmacy: Any, sku: Any, url: Any) -> tuple[str, str]:
    return ((_clean(pharmacy) or "").lower(), (_clean(sku) or _clean(url) or "").lower())


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
                    digemid_composicion=_clean(row.get("digemid_composicion")),
                    restriction_flags_verified=tuple(verified_restriction_flags(row)),
                    label_status=_clean(row.get("label_status")),
                    label_verified_at=_clean(row.get("label_verified_at")),
                    label_verification_source=_clean(row.get("label_verification_source")),
                )
            )

    return products


def _load_compositions(path: Path) -> dict[tuple[str, str], ProductComposition]:
    """Agrupa TODAS las filas del CSV por producto comercial (farmacia + sku/url).

    No aplica los filtros de precio/disponibilidad de `_load_rows`: la seguridad
    debe ver la composición completa aunque alguna fila componente esté incompleta.
    """
    if not path.exists():
        return {}

    ingredients: dict[tuple[str, str], list[str]] = {}
    component_ids: dict[tuple[str, str], list[str]] = {}
    compositions: dict[tuple[str, str], list[str]] = {}
    flags: dict[tuple[str, str], set[str]] = {}

    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            key = composition_key(row.get("pharmacy"), row.get("sku"), row.get("url"))
            if not key[0] or not key[1]:
                continue
            ingredient = _clean(row.get("ingredient"))
            component_id = _clean(row.get("component_id"))
            composition = _clean(row.get("digemid_composicion"))
            if ingredient and ingredient not in ingredients.setdefault(key, []):
                ingredients[key].append(ingredient)
            if component_id and component_id not in component_ids.setdefault(key, []):
                component_ids[key].append(component_id)
            if composition and composition not in compositions.setdefault(key, []):
                compositions[key].append(composition)
            flags.setdefault(key, set()).update(verified_restriction_flags(row))

    return {
        key: ProductComposition(
            ingredients=tuple(ingredients.get(key, [])),
            component_ids=tuple(component_ids.get(key, [])),
            digemid_composicion=" ".join(compositions.get(key, [])),
            restriction_flags_verified=tuple(sorted(flags.get(key, set()))),
        )
        for key in flags
    }


@lru_cache(maxsize=4)
def _catalog_compositions(path_value: str) -> dict[tuple[str, str], ProductComposition]:
    return _load_compositions(Path(path_value))


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
