from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import select

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.db.models import Role
from app.db.session import SessionLocal
from app.repositories.safety_rule_repository import SafetyRuleRepository
from app.repositories.user_repository import UserRepository


ROLES = {
    "user": "Usuario final con historial y feedback.",
    "moderator": "Modera reseñas y contenido generado por usuarios.",
    "admin": "Administra catálogo, usuarios, importaciones y métricas.",
}


def ensure_roles() -> None:
    with SessionLocal() as db:
        for name, description in ROLES.items():
            role = db.scalar(select(Role).where(Role.name == name))
            if role is None:
                db.add(Role(name=name, description=description))
            else:
                role.description = role.description or description
        db.commit()


def ensure_user_from_env(prefix: str, role_name: str) -> None:
    email = os.getenv(f"{prefix}_EMAIL")
    password = os.getenv(f"{prefix}_PASSWORD")
    display_name = os.getenv(f"{prefix}_DISPLAY_NAME", role_name.title())
    if not email or not password:
        return

    with SessionLocal() as db:
        repo = UserRepository(db)
        user = repo.get_by_email(email)
        if user is None:
            user = repo.create_user(email=email, password=password, display_name=display_name)
        repo.assign_role(user, role_name)
        db.commit()
        print(f"{role_name}_user={email}")


def main() -> int:
    ensure_roles()
    with SessionLocal() as db:
        created = SafetyRuleRepository(db).seed_defaults()
        if created:
            print(f"ingredient_safety_rules_created={created}")
    ensure_user_from_env("ADMIN", "admin")
    ensure_user_from_env("MODERATOR", "moderator")
    print("seed_database=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
