from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import RecommendationFeedback, RecommendedPack
from app.domains.reviews.repositorio_metricas_resenas import DEFAULT_REVIEW_SCORE, ReviewMetricsRepository


class RecommendationMetricsRepository:
    def __init__(self, db: Session):
        self.db = db

    def apply_metrics_to_packs(self, packs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        total_pack_exposures = self.db.scalar(select(func.count(RecommendedPack.id))) or 0

        updated = []
        for pack in packs:
            pack_key = str(pack.get("pack_id") or "")
            feedback_score, feedback_count = self._feedback_score(pack_key)
            exposure_score, exposure_count = self._exposure_score(pack_key, total_pack_exposures)
            reviews_score, reviews_count = self._reviews_score(pack)
            products_score = self._products_score(pack)
            diversity_score = self._diversity_score(pack)

            score_gnn = float(pack.get("score_gnn") or pack.get("score") or 0.70)
            score_coverage = float(pack.get("score_coverage") or 1.0)
            score_final = (
                0.30 * score_gnn
                + 0.20 * score_coverage
                + 0.15 * products_score
                + 0.15 * feedback_score
                + 0.10 * reviews_score
                + 0.05 * exposure_score
                + 0.05 * diversity_score
            )

            enriched = dict(pack)
            enriched.update(
                {
                    "score_final": float(score_final),
                    "score": float(score_final),
                    "score_feedback": float(feedback_score),
                    "score_reviews": float(reviews_score),
                    "score_exposure": float(exposure_score),
                    "score_products": float(products_score),
                    "score_diversity": float(diversity_score),
                    "feedback_count": int(feedback_count),
                    "reviews_count": int(reviews_count),
                    "exposure_count": int(exposure_count),
                }
            )
            updated.append(enriched)

        updated.sort(key=lambda item: item.get("score_final") or 0.0, reverse=True)
        for index, pack in enumerate(updated, start=1):
            pack["rank"] = index
        return updated

    def _feedback_score(self, pack_key: str) -> tuple[float, int]:
        if not pack_key:
            return 0.70, 0

        row = self.db.execute(
            select(
                func.avg(RecommendationFeedback.rating),
                func.count(RecommendationFeedback.id),
            ).where(RecommendationFeedback.pack_key == pack_key)
        ).one()
        avg_rating, count = row
        if not avg_rating:
            return 0.70, 0
        return max(0.0, min(1.0, (float(avg_rating) - 1.0) / 4.0)), int(count or 0)

    def _exposure_score(self, pack_key: str, total_pack_exposures: int) -> tuple[float, int]:
        if not pack_key or total_pack_exposures <= 0:
            return 1.0, 0

        count = self.db.scalar(select(func.count(RecommendedPack.id)).where(RecommendedPack.pack_key == pack_key)) or 0
        share = float(count) / max(float(total_pack_exposures), 1.0)
        score = 1.0 - min(0.75, share * 3.0)
        return max(0.25, score), int(count)

    def _reviews_score(self, pack: dict[str, Any]) -> tuple[float, int]:
        products = [product for product in pack.get("selected_products") or [] if isinstance(product, dict)]
        if not products:
            return DEFAULT_REVIEW_SCORE, 0

        scores = []
        review_count = 0
        missing_ids = []
        for product in products:
            if "review_score" in product:
                scores.append(float(product.get("review_score") or DEFAULT_REVIEW_SCORE))
                review_count += int(product.get("review_count") or 0)
            elif product.get("product_id"):
                missing_ids.append(product.get("product_id"))

        if missing_ids:
            metrics = ReviewMetricsRepository(self.db).product_metrics(missing_ids)
            for product_id in missing_ids:
                metric = metrics.get(str(product_id))
                if not metric:
                    continue
                scores.append(float(metric.get("review_score") or DEFAULT_REVIEW_SCORE))
                review_count += int(metric.get("review_count") or 0)

        if not scores:
            return DEFAULT_REVIEW_SCORE, 0
        return sum(scores) / len(scores), review_count

    def _products_score(self, pack: dict[str, Any]) -> float:
        products = [product for product in pack.get("selected_products") or [] if isinstance(product, dict)]
        scores = [float(product.get("product_score")) for product in products if product.get("product_score") is not None]
        if not scores:
            return DEFAULT_REVIEW_SCORE
        return sum(scores) / len(scores)

    def _diversity_score(self, pack: dict[str, Any]) -> float:
        products = [product for product in pack.get("selected_products") or [] if isinstance(product, dict)]
        if len(products) <= 1:
            return 1.0
        pharmacies = [str(product.get("pharmacy") or "") for product in products]
        pharmacy_score = len(set(pharmacies)) / len(pharmacies)
        product_ids = [str(product.get("product_id") or product.get("url") or "") for product in products]
        duplicate_penalty = 1.0 - ((len(product_ids) - len(set(product_ids))) / len(product_ids))
        return max(0.0, min(1.0, 0.70 * pharmacy_score + 0.30 * duplicate_penalty))
