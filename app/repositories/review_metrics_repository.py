from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.orm import Session

from app.db.models import SupplementReview


DEFAULT_AVG_RATING = 3.8
DEFAULT_REVIEW_SCORE = 0.70
DEFAULT_PRIOR_WEIGHT = 10


def rating_to_score(rating: float | None) -> float:
    if rating is None:
        return DEFAULT_REVIEW_SCORE
    return max(0.0, min(1.0, (float(rating) - 1.0) / 4.0))


def _parse_uuid(value: Any) -> UUID | None:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError):
        return None


class ReviewMetricsRepository:
    def __init__(self, db: Session, prior_weight: int = DEFAULT_PRIOR_WEIGHT):
        self.db = db
        self.prior_weight = prior_weight

    def product_metrics(self, product_ids: list[Any]) -> dict[str, dict[str, Any]]:
        ids = []
        for value in product_ids:
            parsed = _parse_uuid(value)
            if parsed is not None and parsed not in ids:
                ids.append(parsed)

        if not ids:
            return {}

        global_avg = self._global_average_rating()
        rows = self.db.execute(
            select(
                SupplementReview.product_id,
                func.avg(SupplementReview.rating).label("avg_rating"),
                func.count(SupplementReview.id).label("review_count"),
                func.sum(cast(SupplementReview.verified_purchase, Integer)).label("verified_review_count"),
            )
            .where(
                SupplementReview.product_id.in_(ids),
                SupplementReview.status == "published",
            )
            .group_by(SupplementReview.product_id)
        ).all()

        by_product = {
            str(product_id): self._build_metrics(
                avg_rating=float(avg_rating or 0.0) if avg_rating else None,
                review_count=int(review_count or 0),
                verified_review_count=int(verified_review_count or 0),
                global_avg=global_avg,
            )
            for product_id, avg_rating, review_count, verified_review_count in rows
        }

        default_metrics = self._build_metrics(
            avg_rating=None,
            review_count=0,
            verified_review_count=0,
            global_avg=global_avg,
        )
        for product_id in ids:
            by_product.setdefault(str(product_id), dict(default_metrics))

        return by_product

    def product_metric(self, product_id: Any) -> dict[str, Any]:
        parsed = _parse_uuid(product_id)
        if parsed is None:
            return self.default_metrics()
        return self.product_metrics([parsed]).get(str(parsed), self.default_metrics())

    def default_metrics(self) -> dict[str, Any]:
        return self._build_metrics(
            avg_rating=None,
            review_count=0,
            verified_review_count=0,
            global_avg=self._global_average_rating(),
        )

    def _global_average_rating(self) -> float:
        avg_rating = self.db.scalar(
            select(func.avg(SupplementReview.rating)).where(SupplementReview.status == "published")
        )
        return float(avg_rating or DEFAULT_AVG_RATING)

    def _build_metrics(
        self,
        *,
        avg_rating: float | None,
        review_count: int,
        verified_review_count: int,
        global_avg: float,
    ) -> dict[str, Any]:
        effective_avg = avg_rating if avg_rating is not None and review_count > 0 else global_avg
        bayesian_rating = (
            effective_avg * review_count + global_avg * self.prior_weight
        ) / max(review_count + self.prior_weight, 1)
        bayesian_score = rating_to_score(bayesian_rating)
        verified_ratio = verified_review_count / review_count if review_count else 0.0

        return {
            "avg_rating": round(float(avg_rating), 4) if avg_rating is not None else None,
            "review_count": int(review_count),
            "verified_review_count": int(verified_review_count),
            "verified_review_ratio": round(float(verified_ratio), 4),
            "bayesian_rating": round(float(bayesian_rating), 4),
            "bayesian_review_score": round(float(bayesian_score), 4),
            "review_score": round(float(bayesian_score), 4),
        }
