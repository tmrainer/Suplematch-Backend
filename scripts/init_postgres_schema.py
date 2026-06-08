from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import select

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.db.database import create_all_tables
from app.db.models import Role
from app.db.session import SessionLocal


BASE_ROLES = {
    "user": "Usuario normal de la app.",
    "moderator": "Revisa reseñas y reportes.",
    "admin": "Administra catálogo, usuarios y métricas.",
}


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description="Crea tablas PostgreSQL y roles base de SupleMatch.")


def seed_roles() -> None:
    with SessionLocal() as db:
        for name, description in BASE_ROLES.items():
            existing = db.scalar(select(Role).where(Role.name == name))
            if existing:
                continue
            db.add(Role(name=name, description=description))
        db.commit()


def main() -> int:
    build_parser().parse_args()
    create_all_tables()
    seed_roles()
    print("postgres_schema=ready")
    print(f"roles={','.join(BASE_ROLES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
