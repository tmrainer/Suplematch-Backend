from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domains.catalog.catalogo_csv import CatalogProduct, _catalog_by_component, _clean
from app.domains.catalog.repositorio_catalogo import CatalogRepository
from app.domains.reviews.repositorio_metricas_resenas import DEFAULT_REVIEW_SCORE, ReviewMetricsRepository
from app.domains.catalog.repositorio_reglas_seguridad import SafetyRuleRepository
from app.domains.catalog.seguridad_productos import (
    evaluate_ingredient_safety,
    infer_restriction_flags,
    product_restriction_flags,
    product_text,
)
from app.db.models import CommercialProduct, Pharmacy, RecommendedPackItem


MAX_PRODUCTS_PER_COMPONENT = 3
COMMERCIAL_SCORE_VERSION = "commercial_ranker_v3_product_reviews"


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
        response["catalog_product_key"] = product.product_key
        response["product_component_count"] = self._csv_product_component_count(product.product_key)
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
            exposure_metrics=None,
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

        exposure_metrics_by_product = self._product_exposure_metrics(products)
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
                exposure_metrics=exposure_metrics_by_product.get(product_id),
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
        exposure_metrics: dict[str, Any] | None,
    ) -> dict[str, Any]:
        match_score = self._match_score(product)
        price_score = self._price_score(product.get("price"))
        stock_score = self._stock_score(product)
        traceability_score = self._traceability_score(product)
        unit_preference_score = self._unit_preference_score(product)
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
        product_exposure_score = float((exposure_metrics or {}).get("product_exposure_score", 1.0))
        pharmacy_exposure_score = float((exposure_metrics or {}).get("pharmacy_exposure_score", 1.0))
        exposure_score = (product_exposure_score * 0.60) + (pharmacy_exposure_score * 0.40)
        quality_flags = self._commercial_quality_flags(product)
        commercial_confidence_score = self._commercial_confidence_score(product)
        catalog_quality_score = self._catalog_quality_score(quality_flags, traceability_score)

        price_stock_score = (price_score + stock_score) / 2.0
        has_budget = self.budget_min is not None or self.budget_max is not None
        if has_budget:
            commercial_score = (
                0.24 * match_score
                + 0.13 * unit_preference_score
                + 0.24 * price_stock_score
                + 0.14 * review_score
                + 0.11 * catalog_quality_score
                + 0.05 * pharmacy_diversity_score
                + 0.04 * freshness_score
                + 0.03 * exposure_score
                + 0.02 * min(verified_review_ratio, 1.0)
                + restriction_boost
                + preferred_boost
                - restriction_penalty
                - ingredient_penalty
                - duplicate_penalty
            )
        else:
            commercial_score = (
                0.26 * match_score
                + 0.14 * unit_preference_score
                + 0.16 * price_stock_score
                + 0.20 * review_score
                + 0.12 * catalog_quality_score
                + 0.06 * pharmacy_diversity_score
                + 0.04 * freshness_score
                + 0.03 * exposure_score
                + 0.03 * min(verified_review_ratio, 1.0)
                + restriction_boost
                + preferred_boost
                - restriction_penalty
                - ingredient_penalty
                - duplicate_penalty
            )
        commercial_score = max(0.0, min(1.0, commercial_score))

        metrics = {
            "match_score": round(match_score, 4),
            "unit_preference_score": round(unit_preference_score, 4),
            "price_score": round(price_score, 4),
            "stock_score": round(stock_score, 4),
            "traceability_score": round(traceability_score, 4),
            "catalog_quality_score": round(catalog_quality_score, 4),
            "commercial_confidence_score": round(commercial_confidence_score, 4),
            "pharmacy_diversity_score": round(pharmacy_diversity_score, 4),
            "freshness_score": round(freshness_score, 4),
            "review_score": round(review_score, 4),
            "product_review_score": round(float((review_metrics or {}).get("product_review_score", review_score)), 4),
            "product_exposure_score": round(product_exposure_score, 4),
            "pharmacy_exposure_score": round(pharmacy_exposure_score, 4),
            "exposure_score": round(exposure_score, 4),
            "product_exposure_count": int((exposure_metrics or {}).get("product_exposure_count", 0)),
            "pharmacy_exposure_count": int((exposure_metrics or {}).get("pharmacy_exposure_count", 0)),
            "restriction_penalty": round(restriction_penalty, 4),
            "ingredient_safety_penalty": round(ingredient_penalty, 4),
            "restriction_boost": round(restriction_boost, 4),
            "preferred_boost": round(preferred_boost, 4),
            "commercial_score": 0.0 if product_safety_blocked else round(commercial_score, 4),
            "product_score": 0.0 if product_safety_blocked else round(commercial_score, 4),
        }
        if review_metrics:
            metrics.update(review_metrics)

        product["restriction_flags"] = product.get("restriction_flags") or product_restriction_flags(product)
        product["restriction_flags_verified"] = product.get("restriction_flags_verified") or []
        product["restriction_flags_inferred"] = product.get("restriction_flags_inferred") or infer_restriction_flags(product)
        product.update(metrics)
        product["commercial_score_version"] = COMMERCIAL_SCORE_VERSION
        product["commercial_quality_flags"] = quality_flags
        product["component_match_type"] = "unit_component" if unit_preference_score >= 0.95 else "multi_component"
        product["commercial_decision"] = "blocked" if product_safety_blocked else "ranked"
        product["product_safety_blocked"] = product_safety_blocked
        product["product_safety_rules"] = ingredient_safety["rules"]
        product["restriction_warnings"] = [*restriction_warnings, *ingredient_safety["warnings"]]
        product["selection_metrics"] = dict(metrics)
        product["commercial_score_breakdown"] = self._commercial_score_breakdown(metrics, has_budget=has_budget)
        product["selection_reasons"] = self._selection_reasons(
            metrics,
            quality_flags,
            product["restriction_warnings"],
            bool(product.get("catalog_preferred")),
        )
        return product

    def _product_exposure_metrics(self, products: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        if self.db is None:
            return {}

        product_ids = [str(product.get("product_id")) for product in products if product.get("product_id")]
        pharmacies = sorted({str(product.get("pharmacy") or "") for product in products if product.get("pharmacy")})
        if not product_ids and not pharmacies:
            return {}

        try:
            total_items = self.db.scalar(select(func.count(RecommendedPackItem.id))) or 0
            product_counts = {
                str(product_id): int(count or 0)
                for product_id, count in self.db.execute(
                    select(RecommendedPackItem.product_id, func.count(RecommendedPackItem.id))
                    .where(RecommendedPackItem.product_id.in_(product_ids))
                    .group_by(RecommendedPackItem.product_id)
                ).all()
            }
            pharmacy_counts = {
                str(pharmacy_name): int(count or 0)
                for pharmacy_name, count in self.db.execute(
                    select(Pharmacy.name, func.count(RecommendedPackItem.id))
                    .join(CommercialProduct, RecommendedPackItem.product_id == CommercialProduct.id)
                    .join(Pharmacy, CommercialProduct.pharmacy_id == Pharmacy.id)
                    .where(Pharmacy.name.in_(pharmacies))
                    .group_by(Pharmacy.name)
                ).all()
            }
        except (AttributeError, SQLAlchemyError, TypeError):
            if hasattr(self.db, "rollback"):
                self.db.rollback()
            return {}

        total = max(float(total_items), 1.0)
        result: dict[str, dict[str, Any]] = {}
        for product in products:
            product_id = str(product.get("product_id") or product.get("url") or "")
            product_count = int(product_counts.get(str(product.get("product_id") or ""), 0) or 0)
            pharmacy = str(product.get("pharmacy") or "")
            pharmacy_count = int(pharmacy_counts.get(pharmacy, 0) or 0)
            product_share = product_count / total
            pharmacy_share = pharmacy_count / total
            result[product_id] = {
                "product_exposure_count": product_count,
                "pharmacy_exposure_count": pharmacy_count,
                "product_exposure_score": max(0.25, 1.0 - min(0.75, product_share * 4.0)),
                "pharmacy_exposure_score": max(0.40, 1.0 - min(0.60, pharmacy_share * 2.5)),
            }
        return result

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

    def _unit_preference_score(self, product: dict[str, Any]) -> float:
        try:
            count = int(float(product.get("product_component_count") or 1))
        except (TypeError, ValueError):
            count = 1
        if count <= 1:
            return 1.0
        if count == 2:
            return 0.78
        if count <= 4:
            return 0.62
        return 0.45

    def _csv_product_component_count(self, product_key: str) -> int:
        return self._csv_product_component_counts().get(product_key, 1)

    def _csv_product_component_counts(self) -> dict[str, int]:
        counts: dict[str, set[str]] = {}
        for products in self._products_by_component().values():
            for product in products:
                counts.setdefault(product.product_key, set()).add(product.component_id)
        return {product_key: max(1, len(component_ids)) for product_key, component_ids in counts.items()}

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

    def _commercial_quality_flags(self, product: dict[str, Any]) -> dict[str, bool]:
        flags = set(product.get("restriction_flags") or product_restriction_flags(product))
        traceability = self._traceability_score(product)
        price = product.get("price")
        stock = product.get("stock")
        availability = str(product.get("availability") or "").lower()
        unit_preference = self._unit_preference_score(product)
        confidence = self._commercial_confidence_score(product)
        return {
            "has_valid_registration": bool(_clean(product.get("registro_sanitario"))),
            "has_traceable_components": traceability >= 0.70,
            "has_verified_label_flags": bool(product.get("restriction_flags_verified")),
            "has_inferred_label_flags": bool(product.get("restriction_flags_inferred") or infer_restriction_flags(product)),
            "has_declared_amount": bool(product.get("amount") or product.get("amount_mg")),
            "has_price": price is not None and self._price_score(price) > 0.05,
            "has_stock_or_availability": "available" in availability or stock is not None,
            "is_unit_component": unit_preference >= 0.95,
            "is_multicomponent": unit_preference < 0.95,
            "contains_fish_or_shellfish": "contains_fish_or_shellfish" in flags,
            "may_contain_gelatin": "may_contain_gelatin" in flags,
            "may_contain_dairy": "may_contain_dairy" in flags,
            "may_contain_soy": "may_contain_soy" in flags,
            "has_gluten_free_claim": "gluten_free_claim" in flags,
            "has_high_commercial_confidence": confidence >= 0.85,
            "has_medium_commercial_confidence": confidence >= 0.68,
        }

    def _catalog_quality_score(self, flags: dict[str, bool], traceability_score: float) -> float:
        score = 0.35 * traceability_score
        score += 0.20 if flags["has_valid_registration"] else 0.0
        score += 0.12 if flags["has_declared_amount"] else 0.0
        score += 0.12 if flags["has_price"] else 0.0
        score += 0.08 if flags["has_stock_or_availability"] else 0.0
        score += 0.08 if flags["has_verified_label_flags"] else 0.0
        score += 0.05 if flags["is_unit_component"] else 0.0
        score += 0.06 if flags.get("has_high_commercial_confidence") else 0.03 if flags.get("has_medium_commercial_confidence") else 0.0
        return max(0.0, min(1.0, score))

    def _commercial_confidence_score(self, product: dict[str, Any]) -> float:
        try:
            score = float(product.get("commercial_confidence_score") or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        if score > 0:
            return max(0.0, min(1.0, score))
        traceability = self._traceability_score(product)
        price_score = 1.0 if product.get("price") is not None else 0.0
        stock_score = 1.0 if "available" in str(product.get("availability") or "").lower() else 0.0
        label_score = 1.0 if product.get("label_verification_source") else 0.35 if product.get("restriction_flags_inferred") else 0.0
        return max(0.0, min(1.0, 0.50 * traceability + 0.20 * price_score + 0.15 * stock_score + 0.15 * label_score))

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
        quality_flags: dict[str, bool],
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
        if quality_flags.get("is_unit_component"):
            reasons.append("Producto unitario priorizado para el componente")
        elif quality_flags.get("is_multicomponent"):
            reasons.append("Producto multicomponente penalizado frente a opciones unitarias")
        if metrics["price_score"] >= 0.70:
            reasons.append("Elegido por mejor precio")
        if metrics["review_score"] >= 0.75 and int(metrics.get("review_count") or 0) > 0:
            reasons.append("Mejor calificación de usuarios para este producto")
        if metrics["traceability_score"] >= 0.85:
            reasons.append("Registro sanitario trazable")
        if metrics.get("commercial_confidence_score", 0) >= 0.85:
            reasons.append("Alta confiabilidad comercial")
        if metrics["pharmacy_diversity_score"] >= 0.90:
            reasons.append("Farmacia distinta para diversificar")
        if metrics["product_exposure_score"] < 0.85 or metrics["pharmacy_exposure_score"] < 0.85:
            reasons.append("Penalizado por exposición repetida")
        if not reasons:
            reasons.append("Opcion comercial disponible para este componente")
        return reasons[:4]

    def _commercial_score_breakdown(self, metrics: dict[str, Any], *, has_budget: bool) -> dict[str, float]:
        price_stock_score = (float(metrics["price_score"]) + float(metrics["stock_score"])) / 2.0
        exposure_score = float(metrics["exposure_score"])
        verified_review_ratio = min(float(metrics.get("verified_review_ratio") or 0.0), 1.0)
        if has_budget:
            return {
                "component_match": round(0.24 * float(metrics["match_score"]), 4),
                "unit_product_preference": round(0.13 * float(metrics["unit_preference_score"]), 4),
                "price_stock": round(0.24 * price_stock_score, 4),
                "product_reviews": round(0.14 * float(metrics["review_score"]), 4),
                "catalog_quality": round(0.11 * float(metrics["catalog_quality_score"]), 4),
                "pharmacy_diversity": round(0.05 * float(metrics["pharmacy_diversity_score"]), 4),
                "freshness": round(0.04 * float(metrics["freshness_score"]), 4),
                "exposure": round(0.03 * exposure_score, 4),
                "verified_reviews": round(0.02 * verified_review_ratio, 4),
                "restriction_penalty": round(-float(metrics["restriction_penalty"]), 4),
                "ingredient_safety_penalty": round(-float(metrics["ingredient_safety_penalty"]), 4),
            }
        return {
            "component_match": round(0.26 * float(metrics["match_score"]), 4),
            "unit_product_preference": round(0.14 * float(metrics["unit_preference_score"]), 4),
            "price_stock": round(0.16 * price_stock_score, 4),
            "product_reviews": round(0.20 * float(metrics["review_score"]), 4),
            "catalog_quality": round(0.12 * float(metrics["catalog_quality_score"]), 4),
            "pharmacy_diversity": round(0.06 * float(metrics["pharmacy_diversity_score"]), 4),
            "freshness": round(0.04 * float(metrics["freshness_score"]), 4),
            "exposure": round(0.03 * exposure_score, 4),
            "verified_reviews": round(0.03 * verified_review_ratio, 4),
            "restriction_penalty": round(-float(metrics["restriction_penalty"]), 4),
            "ingredient_safety_penalty": round(-float(metrics["ingredient_safety_penalty"]), 4),
        }

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
            exposure_metrics=None,
        )
        return float(scored.get("product_score") or 0.0)
