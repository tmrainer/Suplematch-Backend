from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from sqlalchemy import func, select

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from app.core.config import BASE_DIR
from app.db.models import (
    CommercialProduct,
    RecommendationFeedback,
    RecommendationItem,
    RecommendationSession,
    RecommendedPack,
    RecommendedPackItem,
    SupplementReview,
)
from app.db.session import SessionLocal


REPORT_DIR = BASE_DIR / "data/reports/real_feedback"


def _json_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _json_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _pct(part: int | float, total: int | float) -> float:
    if not total:
        return 0.0
    return round(float(part) / float(total), 4)


def build_report(days: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)

    with SessionLocal() as db:
        sessions = list(
            db.scalars(
                select(RecommendationSession)
                .where(RecommendationSession.created_at >= since)
                .order_by(RecommendationSession.created_at.desc())
            )
        )
        feedbacks = list(
            db.scalars(
                select(RecommendationFeedback)
                .where(RecommendationFeedback.created_at >= since)
                .order_by(RecommendationFeedback.created_at.desc())
            )
        )
        reviews = list(
            db.scalars(
                select(SupplementReview)
                .where(SupplementReview.created_at >= since)
                .order_by(SupplementReview.created_at.desc())
            )
        )
        recommendation_items = int(
            db.scalar(
                select(func.count())
                .select_from(RecommendationItem)
                .join(RecommendationSession, RecommendationItem.recommendation_session_id == RecommendationSession.id)
                .where(RecommendationSession.created_at >= since)
            )
            or 0
        )
        pack_items = list(
            db.execute(
                select(RecommendedPackItem.product_id, RecommendedPackItem.product_score, RecommendedPackItem.selection_metrics_json)
                .join(RecommendedPack, RecommendedPackItem.recommended_pack_id == RecommendedPack.id)
                .join(RecommendationSession, RecommendedPack.recommendation_session_id == RecommendationSession.id)
                .where(RecommendationSession.created_at >= since)
            )
        )
        active_products = int(
            db.scalar(
                select(func.count())
                .select_from(CommercialProduct)
                .where(CommercialProduct.commercial_status.in_(["active", "preferred"]))
            )
            or 0
        )

    feedback_with_products = [
        item for item in feedbacks
        if _json_list(item.selected_product_ids_json)
        or _json_list(_json_dict(item.product_context_json).get("selected_products"))
        or item.chosen_product_id is not None
    ]
    chosen_feedback = [item for item in feedbacks if item.chosen_product_id is not None]
    feedback_ratings = [item.rating for item in feedbacks if item.rating is not None]
    review_ratings = [item.rating for item in reviews if item.rating is not None]
    pack_items_with_product = [row for row in pack_items if row.product_id is not None]
    pack_items_with_score = [row for row in pack_items if row.product_score is not None]

    by_condition: dict[str, dict[str, Any]] = {}
    for session in sessions:
        conditions = _json_dict(session.conditions_json).get("conditions") or session.conditions_json
        if isinstance(conditions, dict):
            conditions = list(conditions.keys())
        for condition in _json_list(conditions):
            key = str(condition)
            current = by_condition.setdefault(key, {"condition": key, "sessions": 0, "with_warnings": 0})
            current["sessions"] += 1
            if _json_list(session.profile_warnings_json):
                current["with_warnings"] += 1

    condition_rows = sorted(by_condition.values(), key=lambda item: item["sessions"], reverse=True)
    for row in condition_rows:
        row["warning_rate"] = _pct(row["with_warnings"], row["sessions"])

    summary = {
        "status": "passed",
        "generated_at": now.isoformat(),
        "window_days": days,
        "sessions": len(sessions),
        "recommendation_items": recommendation_items,
        "pack_items": len(pack_items),
        "pack_items_with_product": len(pack_items_with_product),
        "commercial_coverage": _pct(len(pack_items_with_product), len(pack_items)),
        "pack_items_with_score": len(pack_items_with_score),
        "commercial_score_coverage": _pct(len(pack_items_with_score), len(pack_items)),
        "feedback_events": len(feedbacks),
        "feedback_with_products": len(feedback_with_products),
        "feedback_product_context_coverage": _pct(len(feedback_with_products), len(feedbacks)),
        "feedback_chosen_product_events": len(chosen_feedback),
        "avg_feedback_rating": round(mean(feedback_ratings), 4) if feedback_ratings else None,
        "supplement_reviews": len(reviews),
        "published_reviews": sum(1 for item in reviews if item.status == "published"),
        "pending_reviews": sum(1 for item in reviews if item.status == "pending"),
        "hidden_or_rejected_reviews": sum(1 for item in reviews if item.status in {"hidden", "rejected"}),
        "avg_review_rating": round(mean(review_ratings), 4) if review_ratings else None,
        "active_catalog_products": active_products,
        "conditions_observed": len(condition_rows),
        "top_conditions": condition_rows[:10],
    }
    return summary, condition_rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = ["condition", "sessions", "with_warnings", "warning_rate"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evalua senales reales acumuladas para Modelo 1, Modelo 2 y motor comercial.")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--summary-out", type=Path, default=REPORT_DIR / "real_feedback_summary.json")
    parser.add_argument("--conditions-out", type=Path, default=REPORT_DIR / "real_feedback_conditions.csv")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    summary, condition_rows = build_report(args.days)
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(args.conditions_out, condition_rows)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
