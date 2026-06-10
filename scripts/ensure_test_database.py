from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.core.config import settings


SAFE_DB_NAME = re.compile(r"^[a-zA-Z0-9_]+$")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Crea una base PostgreSQL aislada para smoke tests.")
    parser.add_argument("--url", default=settings.DATABASE_URL)
    parser.add_argument("--drop-existing", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    target_url = make_url(args.url)
    db_name = target_url.database
    if not db_name or not SAFE_DB_NAME.fullmatch(db_name):
        raise SystemExit(f"Nombre de base inválido para test: {db_name!r}")

    admin_url = target_url.set(database="postgres")
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT", pool_pre_ping=True)

    with engine.connect() as connection:
        exists = connection.scalar(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": db_name})
        if exists and args.drop_existing:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": db_name},
            )
            connection.execute(text(f'DROP DATABASE "{db_name}"'))
            exists = None

        if not exists:
            connection.execute(text(f'CREATE DATABASE "{db_name}"'))

    print(f"test_database_ready={db_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
