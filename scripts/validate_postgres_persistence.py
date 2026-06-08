from __future__ import annotations

import sys
import argparse
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.db.models import RecommendationFeedback, RecommendationSession, RecommendedPack, Role, User, UserRole
from app.db.session import SessionLocal
from app.repositories.recommendation_metrics_repository import RecommendationMetricsRepository
from app.repositories.user_repository import UserRepository


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        description="Valida persistencia PostgreSQL y efecto de feedback/exposición en re-ranking."
    )


def ensure_user() -> User:
    with SessionLocal() as db:
        repo = UserRepository(db)
        user = repo.get_by_email("validation@suplematch.local")
        if user is None:
            user = repo.create_user(
                email="validation@suplematch.local",
                password="validation-password",
                display_name="Validation User",
            )

        admin_role = db.scalar(select(Role).where(Role.name == "admin"))
        if admin_role is None:
            admin_role = Role(name="admin", description="Administra catálogo, usuarios y métricas.")
            db.add(admin_role)
            db.flush()

        has_admin = any(item.role_id == admin_role.id for item in user.roles)
        if not has_admin:
            db.add(UserRole(user_id=user.id, role_id=admin_role.id))
            db.commit()

        user = repo.get_by_email("validation@suplematch.local")
        if user is None:
            raise RuntimeError("No se pudo crear usuario de validación.")
        return user


def validate_recommendation_persistence(user: User) -> dict:
    with SessionLocal() as db:
        session = RecommendationSession(
            user_id=user.id,
            anonymous_session_id="validation-session",
            recommendation_id=f"rec_validation_{uuid4().hex}",
            input_payload_json={"validation": True},
            conditions_json={"conditions": ["DEFICIT_VIT_D"]},
            model_versions_json={"validation": "manual"},
        )
        db.add(session)
        db.flush()

        pack = RecommendedPack(
            recommendation_session_id=session.id,
            pack_key="pack_validation",
            rank=1,
            score_final=0.70,
            score_gnn=0.70,
            score_coverage=1.0,
            score_feedback=0.70,
        )
        db.add(pack)
        db.flush()

        db.add(
            RecommendationFeedback(
                user_id=user.id,
                recommendation_session_id=session.id,
                recommended_pack_id=pack.id,
                pack_key=pack.pack_key,
                component_ids_json=["COMP_VALIDATION"],
                conditions_context_json=["DEFICIT_VIT_D"],
                rating=5,
                was_relevant=True,
                would_follow=True,
                comment="validation",
            )
        )
        db.commit()

        metrics = RecommendationMetricsRepository(db).apply_metrics_to_packs(
            [
                {
                    "pack_id": "pack_validation",
                    "rank": 1,
                    "score_gnn": 0.70,
                    "score_coverage": 1.0,
                    "selected_products": [],
                }
            ]
        )[0]

        return {
            "recommendation_id": session.recommendation_id,
            "pack_key": pack.pack_key,
            "score_feedback": metrics["score_feedback"],
            "feedback_count": metrics["feedback_count"],
            "score_exposure": metrics["score_exposure"],
            "exposure_count": metrics["exposure_count"],
            "score_final": metrics["score_final"],
        }


def main() -> int:
    build_parser().parse_args()
    user = ensure_user()
    result = validate_recommendation_persistence(user)
    print("postgres_persistence=ok")
    for key, value in result.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
