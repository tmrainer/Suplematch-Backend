"""Redacta reportes de laboratorio mas antiguos que la politica de retencion (LAB_REPORT_RETENTION_DAYS).

Uso:
    python scripts/ops/purgar_lab_reports.py --dry-run          # solo cuenta
    python scripts/ops/purgar_lab_reports.py                    # redacta con settings.LAB_REPORT_RETENTION_DAYS
    python scripts/ops/purgar_lab_reports.py --days 180         # umbral explicito

Pensado para un cron diario. No borra filas: deja status=deleted + deleted_at (ver docs/privacy_and_safety.md).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import func, select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.models import LabReport  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.domains.labs.servicio_analisis_examenes import LabAnalysisService  # noqa: E402


def count_expired(db, threshold: datetime) -> int:
    return int(
        db.scalar(
            select(func.count(LabReport.id)).where(LabReport.created_at < threshold, LabReport.status != "deleted")
        )
        or 0
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=None, help="Dias de retencion (default: LAB_REPORT_RETENTION_DAYS).")
    parser.add_argument("--dry-run", action="store_true", help="Solo informa cuantos reportes se redactarian.")
    args = parser.parse_args(argv)

    days = args.days if args.days is not None else settings.LAB_REPORT_RETENTION_DAYS
    if days <= 0:
        print(json.dumps({"status": "skipped", "reason": "retention_days <= 0", "retention_days": days}))
        return 0

    now = datetime.now(timezone.utc)
    threshold = now - timedelta(days=days)
    with SessionLocal() as db:
        pending = count_expired(db, threshold)
        redacted = 0
        if not args.dry_run and pending:
            redacted = LabAnalysisService(db).purge_expired(now=now, retention_days=days)

    print(
        json.dumps(
            {
                "status": "dry_run" if args.dry_run else "done",
                "retention_days": days,
                "threshold": threshold.isoformat(),
                "expired_reports": pending,
                "redacted_reports": redacted,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
