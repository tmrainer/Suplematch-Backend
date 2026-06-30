#!/usr/bin/env python3
"""Evalua si hay datos reales suficientes para reentrenar Modelo 1.

No reentrena. Solo consulta PostgreSQL y emite una decision operativa:
`ready=false` mantiene el modelo actual y sugiere usar feedback para reranking
o calibracion de thresholds antes de tocar el clasificador.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import create_engine, text


ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from app.core.config import settings


COUNT_QUERIES = {
    "recommendation_sessions": "select count(*) from recommendation_sessions",
    "recommendation_feedback": "select count(*) from recommendation_feedback",
    "supplement_reviews": "select count(*) from supplement_reviews",
    "lab_reports": "select count(*) from lab_reports where status != 'deleted'",
}


def count_table(connection, query: str) -> int:
    try:
        return int(connection.execute(text(query)).scalar() or 0)
    except Exception:
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Evalua readiness de reentrenamiento con datos reales.")
    parser.add_argument("--min-sessions", type=int, default=500)
    parser.add_argument("--min-feedback", type=int, default=150)
    parser.add_argument("--min-lab-reports", type=int, default=50)
    parser.add_argument("--min-reviews", type=int, default=50)
    parser.add_argument("--fail-if-not-ready", action="store_true")
    args = parser.parse_args()

    engine = create_engine(str(settings.DATABASE_URL))
    with engine.connect() as connection:
        counts = {
            name: count_table(connection, query)
            for name, query in COUNT_QUERIES.items()
        }

    checks = {
        "sessions_ready": counts["recommendation_sessions"] >= args.min_sessions,
        "feedback_ready": counts["recommendation_feedback"] >= args.min_feedback,
        "labs_ready": counts["lab_reports"] >= args.min_lab_reports,
        "reviews_ready": counts["supplement_reviews"] >= args.min_reviews,
    }
    ready = all(checks.values())
    recommendation = (
        "ready_for_retraining"
        if ready
        else "do_not_retrain_use_thresholds_and_reranker"
    )
    result = {
        "ready": ready,
        "recommendation": recommendation,
        "counts": counts,
        "thresholds": {
            "min_sessions": args.min_sessions,
            "min_feedback": args.min_feedback,
            "min_lab_reports": args.min_lab_reports,
            "min_reviews": args.min_reviews,
        },
        "checks": checks,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.fail_if_not_ready and not ready:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
