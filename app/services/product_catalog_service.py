from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.catalog_repository import CatalogRepository
from app.repositories.review_metrics_repository import DEFAULT_REVIEW_SCORE, ReviewMetricsRepository
from app.repositories.safety_rule_repository import SafetyRuleRepository
from app.services.product_safety import (
    evaluate_ingredient_safety,
    infer_restriction_flags,
    product_restriction_flags,
    product_text,
)


MAX_PRODUCTS_PER_COMPONENT = 3


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
            "regulatory_status": self.regulatory_status,
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
                    regulatory_status=_clean(row.get("regulatory_status")) or "digemid_match",
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


class ProductCatalogService:
    def __init__(
        self,
        catalog_path: Path | None = None,
        db: Session | None = None,
        budget_min: float | None = None,
        budget_max: float | None = None,
        restrictions: list[str] | None = None,
        safety_conditions: list[str] | None = None,
    ):
        self.catalog_path = catalog_path or settings.APPROVED_CATALOG_PATH
        self.db = db
        self.budget_min = budget_min
        self.budget_max = budget_max
        self.restrictions = restrictions or []
        self.safety_conditions = safety_conditions or []
        self.review_metrics = ReviewMetricsRepository(db) if db is not None else None
        self._safety_rules_cache = None

    def products_for_component(
        self,
        component_id: str | None,
        limit: int = MAX_PRODUCTS_PER_COMPONENT,
    ) -> list[dict[str, Any]]:
        if not component_id:
            return []

        if self.db is not None:
            products = CatalogRepository(self.db).products_for_component(component_id, limit=50)
            products = self._score_product_dicts(
                products,
                used_pharmacies={},
                used_rs=set(),
                used_product_ids=set(),
            )
            products = [product for product in products if not product.get("product_safety_blocked")]
            products = sorted(products, key=lambda product: float(product.get("product_score") or 0.0), reverse=True)
            return self._diverse_product_dicts(products, limit)

        products = self._products_by_component().get(component_id, [])
        scored = [
            self._score_catalog_product(product, used_pharmacies={}, used_rs=set(), used_product_keys=set())
            for product in products
        ]
        scored = [product for product in scored if not product.get("product_safety_blocked")]
        scored = sorted(scored, key=lambda product: float(product.get("product_score") or 0.0), reverse=True)
        return self._diverse_product_dicts(scored, limit)

    def select_products_for_pack(
        self,
        component_ids: list[str],
        limit_per_component: int = 1,
    ) -> list[dict[str, Any]]:
        if self.db is not None:
            return self._select_products_for_pack_from_db(component_ids, limit_per_component)

        selected: list[dict[str, Any]] = []
        used_pharmacies: dict[str, int] = {}
        used_rs: set[str] = set()
        used_product_keys: set[str] = set()

        for component_id in component_ids:
            candidates = self._products_by_component().get(component_id, [])
            if not candidates:
                continue

            ranked = sorted(
                candidates,
                key=lambda product: self._pack_product_score(
                    product,
                    used_pharmacies=used_pharmacies,
                    used_rs=used_rs,
                    used_product_keys=used_product_keys,
                ),
                reverse=True,
            )

            picked_for_component = 0
            for product in ranked:
                if product.product_key in used_product_keys:
                    continue

                scored_product = self._score_catalog_product(
                    product,
                    used_pharmacies=used_pharmacies,
                    used_rs=used_rs,
                    used_product_keys=used_product_keys,
                )
                if scored_product.get("product_safety_blocked"):
                    continue

                selected.append(scored_product)
                used_product_keys.add(product.product_key)
                used_rs.add(product.registro_sanitario)
                used_pharmacies[product.pharmacy] = used_pharmacies.get(product.pharmacy, 0) + 1
                picked_for_component += 1

                if picked_for_component >= limit_per_component:
                    break

        return selected

    def _select_products_for_pack_from_db(
        self,
        component_ids: list[str],
        limit_per_component: int,
    ) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        used_pharmacies: dict[str, int] = {}
        used_rs: set[str] = set()
        used_product_ids: set[str] = set()
        repo = CatalogRepository(self.db)

        for component_id in component_ids:
            candidates = repo.products_for_component(component_id, limit=50)
            if not candidates:
                continue
            candidates = self._score_product_dicts(
                candidates,
                used_pharmacies=used_pharmacies,
                used_rs=used_rs,
                used_product_ids=used_product_ids,
            )
            candidates = [product for product in candidates if not product.get("product_safety_blocked")]

            ranked = sorted(
                candidates,
                key=lambda product: float(product.get("product_score") or 0.0),
                reverse=True,
            )

            picked_for_component = 0
            for product in ranked:
                product_id = str(product.get("product_id") or product.get("url"))
                if product_id in used_product_ids:
                    continue

                selected.append(product)
                used_product_ids.add(product_id)
                if product.get("registro_sanitario"):
                    used_rs.add(str(product["registro_sanitario"]))
                pharmacy = str(product.get("pharmacy") or "")
                used_pharmacies[pharmacy] = used_pharmacies.get(pharmacy, 0) + 1
                picked_for_component += 1

                if picked_for_component >= limit_per_component:
                    break

        return selected

    def _products_by_component(self) -> dict[str, list[CatalogProduct]]:
        return _catalog_by_component(str(self.catalog_path))

    def _diverse_products(
        self,
        products: list[CatalogProduct],
        limit: int,
    ) -> list[CatalogProduct]:
        selected: list[CatalogProduct] = []
        seen_pharmacies = set()

        for product in products:
            if len(selected) >= limit:
                break

            if product.pharmacy in seen_pharmacies:
                continue

            selected.append(product)
            seen_pharmacies.add(product.pharmacy)

        if len(selected) < limit:
            selected_keys = {product.product_key for product in selected}
            for product in products:
                if len(selected) >= limit:
                    break

                if product.product_key in selected_keys:
                    continue

                selected.append(product)
                selected_keys.add(product.product_key)

        return selected

    def _diverse_product_dicts(
        self,
        products: list[dict[str, Any]],
        limit: int,
    ) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        seen_pharmacies = set()

        for product in products:
            if len(selected) >= limit:
                break

            pharmacy = product.get("pharmacy")
            if pharmacy in seen_pharmacies:
                continue

            selected.append(product)
            seen_pharmacies.add(pharmacy)

        if len(selected) < limit:
            selected_ids = {product.get("product_id") or product.get("url") for product in selected}
            for product in products:
                if len(selected) >= limit:
                    break

                product_id = product.get("product_id") or product.get("url")
                if product_id in selected_ids:
                    continue

                selected.append(product)
                selected_ids.add(product_id)

        return selected

    def _pack_product_score(
        self,
        product: CatalogProduct,
        *,
        used_pharmacies: dict[str, int],
        used_rs: set[str],
        used_product_keys: set[str],
    ) -> float:
        scored = self._score_catalog_product(
            product,
            used_pharmacies=used_pharmacies,
            used_rs=used_rs,
            used_product_keys=used_product_keys,
        )
        duplicate_penalty = 1.0 if product.product_key in used_product_keys else 0.0
        return float(scored.get("product_score") or 0.0) - duplicate_penalty

    def _score_catalog_product(
        self,
        product: CatalogProduct,
        *,
        used_pharmacies: dict[str, int],
        used_rs: set[str],
        used_product_keys: set[str],
    ) -> dict[str, Any]:
        response = product.to_response()
        response["stock"] = None
        response["last_seen_at"] = None
        response["restriction_flags_inferred"] = infer_restriction_flags(response)
        response["restriction_flags_verified"] = []
        response["restriction_flags"] = response["restriction_flags_inferred"]
        duplicate_penalty = 1.0 if product.product_key in used_product_keys else 0.0
        return self._apply_product_scores(
            response,
            review_metrics={
                "review_score": DEFAULT_REVIEW_SCORE,
                "bayesian_review_score": DEFAULT_REVIEW_SCORE,
                "review_count": 0,
                "avg_rating": None,
                "verified_review_count": 0,
                "verified_review_ratio": 0.0,
            },
            used_pharmacies=used_pharmacies,
            used_rs=used_rs,
            duplicate_penalty=duplicate_penalty,
        )

    def _score_product_dicts(
        self,
        products: list[dict[str, Any]],
        *,
        used_pharmacies: dict[str, int],
        used_rs: set[str],
        used_product_ids: set[str],
    ) -> list[dict[str, Any]]:
        review_metrics_by_product = {}
        if self.review_metrics is not None:
            review_metrics_by_product = self.review_metrics.product_metrics(
                [product.get("product_id") for product in products if product.get("product_id")]
            )

        scored = []
        for product in products:
            product_id = str(product.get("product_id") or product.get("url") or "")
            duplicate_penalty = 1.0 if product_id in used_product_ids else 0.0
            scored_product = self._apply_product_scores(
                dict(product),
                review_metrics=review_metrics_by_product.get(product_id),
                used_pharmacies=used_pharmacies,
                used_rs=used_rs,
                duplicate_penalty=duplicate_penalty,
            )
            scored.append(scored_product)
        return scored

    def _apply_product_scores(
        self,
        product: dict[str, Any],
        *,
        review_metrics: dict[str, Any] | None,
        used_pharmacies: dict[str, int],
        used_rs: set[str],
        duplicate_penalty: float,
    ) -> dict[str, Any]:
        match_score = self._match_score(product)
        price_score = self._price_score(product.get("price"))
        stock_score = self._stock_score(product)
        traceability_score = self._traceability_score(product)
        pharmacy_diversity_score = self._pharmacy_diversity_score(product, used_pharmacies)
        freshness_score = self._freshness_score(product.get("last_seen_at"))
        restriction_penalty, restriction_warnings, restriction_boost = self._restriction_adjustment(product)
        ingredient_safety = evaluate_ingredient_safety(
            product,
            restrictions=self.restrictions,
            safety_conditions=self.safety_conditions,
            rules=self._active_safety_rules(),
        )
        ingredient_penalty = float(ingredient_safety["penalty"])
        product_safety_blocked = bool(ingredient_safety["blocked"])
        preferred_boost = 0.04 if product.get("catalog_preferred") else 0.0
        review_score = float((review_metrics or {}).get("review_score", DEFAULT_REVIEW_SCORE))
        verified_review_ratio = float((review_metrics or {}).get("verified_review_ratio", 0.0))

        price_stock_score = (price_score + stock_score) / 2.0
        has_budget = self.budget_min is not None or self.budget_max is not None
        if has_budget:
            product_score = (
                0.28 * match_score
                + 0.30 * price_stock_score
                + 0.16 * review_score
                + 0.13 * traceability_score
                + 0.08 * pharmacy_diversity_score
                + 0.05 * freshness_score
                + 0.02 * min(verified_review_ratio, 1.0)
                + restriction_boost
                + preferred_boost
                - restriction_penalty
                - ingredient_penalty
                - duplicate_penalty
            )
        else:
            product_score = (
                0.30 * match_score
                + 0.20 * price_stock_score
                + 0.20 * review_score
                + 0.15 * traceability_score
                + 0.10 * pharmacy_diversity_score
                + 0.05 * freshness_score
                + 0.03 * min(verified_review_ratio, 1.0)
                + restriction_boost
                + preferred_boost
                - restriction_penalty
                - ingredient_penalty
                - duplicate_penalty
            )

        metrics = {
            "match_score": round(match_score, 4),
            "price_score": round(price_score, 4),
            "stock_score": round(stock_score, 4),
            "traceability_score": round(traceability_score, 4),
            "pharmacy_diversity_score": round(pharmacy_diversity_score, 4),
            "freshness_score": round(freshness_score, 4),
            "review_score": round(review_score, 4),
            "restriction_penalty": round(restriction_penalty, 4),
            "ingredient_safety_penalty": round(ingredient_penalty, 4),
            "restriction_boost": round(restriction_boost, 4),
            "preferred_boost": round(preferred_boost, 4),
            "product_score": 0.0 if product_safety_blocked else round(max(0.0, min(1.0, product_score)), 4),
        }
        if review_metrics:
            metrics.update(review_metrics)

        product["restriction_flags"] = product.get("restriction_flags") or product_restriction_flags(product)
        product["restriction_flags_verified"] = product.get("restriction_flags_verified") or []
        product["restriction_flags_inferred"] = product.get("restriction_flags_inferred") or infer_restriction_flags(product)
        product.update(metrics)
        product["product_safety_blocked"] = product_safety_blocked
        product["product_safety_rules"] = ingredient_safety["rules"]
        product["restriction_warnings"] = [*restriction_warnings, *ingredient_safety["warnings"]]
        product["selection_metrics"] = dict(metrics)
        product["selection_reasons"] = self._selection_reasons(
            metrics,
            product["restriction_warnings"],
            bool(product.get("catalog_preferred")),
        )
        return product

    def _active_safety_rules(self):
        if self._safety_rules_cache is not None:
            return self._safety_rules_cache
        if self.db is None:
            self._safety_rules_cache = None
            return None
        try:
            self._safety_rules_cache = SafetyRuleRepository(self.db).active_rules() or None
        except (AttributeError, SQLAlchemyError):
            if hasattr(self.db, "rollback"):
                self.db.rollback()
            self._safety_rules_cache = None
        return self._safety_rules_cache

    def _restriction_adjustment(self, product: dict[str, Any]) -> tuple[float, list[str], float]:
        restrictions = set(self.restrictions or [])
        if not restrictions or "sin_restricciones" in restrictions:
            return 0.0, [], 0.0

        flags = set(product.get("restriction_flags") or product_restriction_flags(product))
        text = product_text(product)

        penalty = 0.0
        boost = 0.0
        warnings: list[str] = []

        if "alergia_pescado_mariscos" in restrictions and (
            "contains_fish_or_shellfish" in flags
            or any(keyword in text for keyword in ("fish", "pescado", "marino", "aceite de pescado"))
        ):
            penalty += 0.35
            warnings.append("Advertencia por alergia a pescado/mariscos")

        if "evita_gelatina" in restrictions and (
            "may_contain_gelatin" in flags
            or any(
                keyword in text
                for keyword in (
                    "gelatina",
                    "softgel",
                    "cápsula blanda",
                    "capsula blanda",
                    "cápsulas blandas",
                    "capsulas blandas",
                )
            )
        ):
            penalty += 0.22
            warnings.append("Puede contener cápsula blanda o gelatina")

        if "alergia_lacteos" in restrictions and (
            "may_contain_dairy" in flags
            or any(keyword in text for keyword in ("lacteo", "lácteo", "leche", "whey", "suero de leche", "caseina", "caseína"))
        ):
            penalty += 0.30
            warnings.append("Advertencia por alergia a lácteos")

        if "alergia_soya" in restrictions and (
            "may_contain_soy" in flags
            or any(keyword in text for keyword in ("soya", "soy", "lecitina de soya"))
        ):
            penalty += 0.25
            warnings.append("Advertencia por alergia a soya")

        if "sin_gluten" in restrictions:
            traceability_score = self._traceability_score(product)
            if traceability_score >= 0.85:
                boost += 0.03
            else:
                penalty += 0.08
                warnings.append("Sin gluten: trazabilidad insuficiente, revisar etiqueta")

        return min(0.70, penalty), warnings, min(0.05, boost)

    def _match_score(self, product: dict[str, Any]) -> float:
        try:
            raw = float(product.get("component_match_score") or 85.0)
        except (TypeError, ValueError):
            raw = 85.0
        return max(0.0, min(1.0, raw / 100.0))

    def _price_score(self, value: Any) -> float:
        try:
            price = float(value or 0.0)
        except (TypeError, ValueError):
            return 0.65
        if price <= 0:
            return 0.65

        budget_max = self.budget_max
        budget_min = self.budget_min

        if budget_max is not None and price > budget_max:
            excess_ratio = (price - budget_max) / max(budget_max, 1.0)
            return max(0.05, 0.4 * (1.0 - min(1.0, excess_ratio)))

        if budget_min is not None and budget_max is not None:
            range_size = max(budget_max - budget_min, 1.0)
            position = (price - budget_min) / range_size
            return max(0.0, min(1.0, 1.0 - 0.30 * position))

        if budget_max is not None:
            return max(0.30, min(1.0, 1.0 - (price / budget_max) * 0.30))

        return max(0.05, min(1.0, 1.0 / (1.0 + price / 100.0)))

    def _stock_score(self, product: dict[str, Any]) -> float:
        availability = str(product.get("availability") or "").lower()
        stock = product.get("stock")
        if "available" not in availability:
            return 0.25
        try:
            stock_value = int(stock)
        except (TypeError, ValueError):
            return 0.75
        if stock_value <= 0:
            return 0.40
        if stock_value < 5:
            return 0.75
        return 1.0

    def _traceability_score(self, product: dict[str, Any]) -> float:
        status = str(product.get("regulatory_status") or "").lower()
        registro = _clean(product.get("registro_sanitario"))
        if registro and ("digemid" in status or "match" in status):
            return 1.0
        if registro:
            return 0.85
        if "trace" in status or "match" in status:
            return 0.70
        return 0.45

    def _pharmacy_diversity_score(self, product: dict[str, Any], used_pharmacies: dict[str, int]) -> float:
        pharmacy = str(product.get("pharmacy") or "")
        return max(0.35, 1.0 - 0.20 * used_pharmacies.get(pharmacy, 0))

    def _freshness_score(self, last_seen_at: Any) -> float:
        if not last_seen_at:
            return 0.70
        if isinstance(last_seen_at, datetime):
            seen_at = last_seen_at
        else:
            try:
                seen_at = datetime.fromisoformat(str(last_seen_at).replace("Z", "+00:00"))
            except ValueError:
                return 0.70
        if seen_at.tzinfo is None:
            seen_at = seen_at.replace(tzinfo=timezone.utc)
        age_days = max(0, (datetime.now(timezone.utc) - seen_at).days)
        if age_days <= 7:
            return 1.0
        if age_days <= 30:
            return 0.85
        if age_days <= 90:
            return 0.65
        return 0.45

    def _selection_reasons(
        self,
        metrics: dict[str, Any],
        restriction_warnings: list[str] | None = None,
        preferred: bool = False,
    ) -> list[str]:
        reasons = []
        if restriction_warnings:
            reasons.extend(restriction_warnings[:2])
        if preferred:
            reasons.append("Producto preferido por control de catálogo")
        if metrics["match_score"] >= 0.85:
            reasons.append("Buen match con el componente recomendado")
        if metrics["price_score"] >= 0.70:
            reasons.append("Elegido por mejor precio")
        if metrics["review_score"] >= 0.75 and int(metrics.get("review_count") or 0) > 0:
            reasons.append("Mejor score de reviews")
        if metrics["traceability_score"] >= 0.85:
            reasons.append("Registro sanitario trazable")
        if metrics["pharmacy_diversity_score"] >= 0.90:
            reasons.append("Farmacia distinta para diversificar")
        if not reasons:
            reasons.append("Opcion comercial disponible para este componente")
        return reasons[:4]

    def _pack_product_dict_score(
        self,
        product: dict[str, Any],
        *,
        used_pharmacies: dict[str, int],
        used_rs: set[str],
        used_product_ids: set[str],
    ) -> float:
        product_id = str(product.get("product_id") or product.get("url") or "")
        duplicate_penalty = 1.0 if product_id in used_product_ids else 0.0
        scored = self._apply_product_scores(
            dict(product),
            review_metrics=None,
            used_pharmacies=used_pharmacies,
            used_rs=used_rs,
            duplicate_penalty=duplicate_penalty,
        )
        return float(scored.get("product_score") or 0.0)
