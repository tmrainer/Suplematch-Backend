"""Pobla la cola de revisión humana de RS (`catalog_rs_reviews`) desde approved_catalog.csv
sin reimportar el catálogo. Ver docs/catalog_rs_review.md.

Uso:
    python scripts/ops/poblar_cola_revision_rs.py --dry-run
    python scripts/ops/poblar_cola_revision_rs.py --sample-ratio 0.05
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from app.core.config import settings
from app.core.observability import log_event
from app.db.session import SessionLocal
from app.domains.admin.repositorio_revision_rs import CatalogRsReviewRepository
from app.domains.admin.servicio_revision_rs import (
    DEFAULT_SAMPLE_RATIO,
    DEFAULT_SAMPLE_SEED,
    select_review_items,
    summarize_items,
)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pobla la cola de revisión humana de RS inferidos.")
    parser.add_argument("--catalog", type=Path, default=settings.APPROVED_CATALOG_PATH)
    parser.add_argument("--sample-ratio", type=float, default=DEFAULT_SAMPLE_RATIO)
    parser.add_argument("--seed", default=DEFAULT_SAMPLE_SEED)
    parser.add_argument("--dry-run", action="store_true", help="Calcula y reporta sin escribir en la BD.")
    parser.add_argument("--json", action="store_true", help="Imprime el resumen en JSON.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows = read_rows(args.catalog)
    items = select_review_items(rows, sample_ratio=args.sample_ratio, seed=args.seed)
    selection = summarize_items(items)

    with SessionLocal() as db:
        stats = CatalogRsReviewRepository(db).upsert_items(items, dry_run=args.dry_run)
        if args.dry_run:
            db.rollback()
        else:
            db.commit()

    result = {
        "catalog": str(args.catalog),
        "rows": len(rows),
        "dry_run": args.dry_run,
        "selected_inferred": selection.get("inferred", 0),
        "selected_random_sample": selection.get("random_sample", 0),
        **stats,
    }
    log_event("catalog_rs_review_queue_populated", **result)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for key, value in result.items():
            print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
