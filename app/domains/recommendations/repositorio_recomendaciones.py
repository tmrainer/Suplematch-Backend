from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    CommercialProduct,
    Component,
    Pharmacy,
    RecommendationItem,
    RecommendationSession,
    RecommendedPack,
    RecommendedPackItem,
)


def _clean(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _pharmacy_slug(value: str | None) -> str | None:
    text = _clean(value)
    if text is None:
        return None

    return "".join(char.lower() if char.isalnum() else "-" for char in text).strip("-")


class RecommendationRepository:
    def __init__(self, db: Session):
        self.db = db
        self._component_cache: dict[str, Component | None] = {}
        self._product_cache: dict[tuple[str, str], CommercialProduct | None] = {}

    def save_response(
        self,
        *,
        recommendation_id: str,
        session_id: str | None,
        input_payload: dict[str, Any],
        conditions: list[str],
        model_versions: dict[str, str],
        profile_warnings: list[str] | None,
        recommendations: list[dict[str, Any]],
        packs_ranked: list[dict[str, Any]],
        user_id: UUID | None = None,
        anonymous_session_id: str | None = None,
    ) -> RecommendationSession:
        session = RecommendationSession(
            user_id=user_id,
            anonymous_session_id=anonymous_session_id or session_id,
            recommendation_id=recommendation_id,
            input_payload_json=input_payload,
            conditions_json={"conditions": conditions},
            profile_warnings_json=profile_warnings or [],
            model_versions_json=model_versions,
        )
        self.db.add(session)
        self.db.flush()

        for index, item in enumerate(recommendations, start=1):
            external_component_id = _clean(item.get("component_id"))
            self.db.add(
                RecommendationItem(
                    recommendation_session_id=session.id,
                    component_id=self._component_pk(external_component_id),
                    external_component_id=external_component_id,
                    component_name=_clean(item.get("name") or item.get("display_name")),
                    rank=index,
                    reason=_clean(item.get("reason")),
                    score_model=item.get("score"),
                    recommendation_type=_clean(item.get("type") or item.get("priority")),
                    condition_code=_clean(item.get("condition")),
                )
            )

        for pack in packs_ranked:
            db_pack = RecommendedPack(
                recommendation_session_id=session.id,
                pack_key=_clean(pack.get("pack_id")) or f"pack_{pack.get('rank') or 0}",
                rank=int(pack.get("rank") or 0),
                score_final=pack.get("score_final") or pack.get("score"),
                score_gnn=pack.get("score_gnn"),
                score_coverage=pack.get("score_coverage"),
                score_feedback=pack.get("score_feedback"),
                score_reviews=pack.get("score_reviews"),
                score_exposure=pack.get("score_exposure"),
                score_products=pack.get("score_products"),
                score_diversity=pack.get("score_diversity"),
            )
            self.db.add(db_pack)
            self.db.flush()
            self._save_pack_items(db_pack, pack)

        self.db.commit()
        self.db.refresh(session)
        return session

    def _save_pack_items(self, db_pack: RecommendedPack, pack: dict[str, Any]) -> None:
        selected_products = pack.get("selected_products") or []
        product_by_component = {
            _clean(product.get("component_id")): product
            for product in selected_products
            if isinstance(product, dict)
        }

        components = pack.get("components") or []
        for index, component in enumerate(components, start=1):
            if not isinstance(component, dict):
                continue

            external_component_id = _clean(component.get("component_id"))
            selected_product = product_by_component.get(external_component_id) or {}
            self.db.add(
                RecommendedPackItem(
                    recommended_pack_id=db_pack.id,
                    component_id=self._component_pk(external_component_id),
                    external_component_id=external_component_id,
                    component_name=_clean(component.get("name") or component.get("display_name")),
                    product_id=self._product_pk(selected_product),
                    price_at_recommendation=selected_product.get("price"),
                    availability_at_recommendation=_clean(selected_product.get("availability")),
                    product_score=_float(selected_product.get("product_score")),
                    match_score=_float(selected_product.get("match_score")),
                    review_score=_float(selected_product.get("review_score")),
                    review_count=_int(selected_product.get("review_count")),
                    avg_rating=_float(selected_product.get("avg_rating")),
                    bayesian_review_score=_float(selected_product.get("bayesian_review_score")),
                    price_score=_float(selected_product.get("price_score")),
                    stock_score=_float(selected_product.get("stock_score")),
                    traceability_score=_float(selected_product.get("traceability_score")),
                    pharmacy_diversity_score=_float(selected_product.get("pharmacy_diversity_score")),
                    freshness_score=_float(selected_product.get("freshness_score")),
                    selection_metrics_json=selected_product.get("selection_metrics") or {},
                    rank=index,
                )
            )

    def _component_pk(self, external_component_id: str | None):
        if external_component_id is None:
            return None

        if external_component_id not in self._component_cache:
            self._component_cache[external_component_id] = self.db.scalar(
                select(Component).where(Component.component_id == external_component_id)
            )

        component = self._component_cache[external_component_id]
        return component.id if component else None

    def _product_pk(self, product: dict[str, Any]):
        product_id = _clean(product.get("product_id"))
        if product_id is not None:
            try:
                parsed_id = UUID(product_id)
            except ValueError:
                parsed_id = None
            if parsed_id is not None:
                product_row = self.db.get(CommercialProduct, parsed_id)
                if product_row is not None:
                    return product_row.id

        pharmacy_slug = _pharmacy_slug(product.get("pharmacy"))
        sku = _clean(product.get("sku")) or _clean(product.get("url"))
        if pharmacy_slug is None or sku is None:
            return None

        cache_key = (pharmacy_slug, sku)
        if cache_key not in self._product_cache:
            self._product_cache[cache_key] = self.db.scalar(
                select(CommercialProduct)
                .join(Pharmacy, CommercialProduct.pharmacy_id == Pharmacy.id)
                .where(Pharmacy.slug == pharmacy_slug, CommercialProduct.sku == sku)
            )

        product_row = self._product_cache[cache_key]
        return product_row.id if product_row else None
