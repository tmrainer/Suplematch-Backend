from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import RecommendationSession, User, UserPersonalInfo, utcnow
from app.domains.labs.servicio_analisis_examenes import LabAnalysisService
from app.domains.users.repositorio_usuarios import UserRepository, user_roles
from app.domains.users.esquemas import (
    UserHealthDataDeleteOut,
    UserHealthDataExportOut,
    UserOut,
    UserPersonalInfoOut,
    UserPersonalInfoUpdate,
    UserProfileOut,
    UserProfileUpdate,
    UserUpdate,
)


def to_personal_info_out(personal_info: UserPersonalInfo | None) -> UserPersonalInfoOut | None:
    if personal_info is None:
        return None
    return UserPersonalInfoOut(
        first_name=personal_info.first_name,
        last_name=personal_info.last_name,
        phone=personal_info.phone,
        country=personal_info.country,
        city=personal_info.city,
        district=personal_info.district,
        address_line=personal_info.address_line,
        date_of_birth=personal_info.date_of_birth,
        document_type=personal_info.document_type,
        document_number=personal_info.document_number,
        preferences=personal_info.preferences_json or {},
        created_at=personal_info.created_at,
        updated_at=personal_info.updated_at,
    )


def to_user_out(user: User) -> UserOut:
    profile = None
    if user.profile is not None:
        profile = UserProfileOut(
            birth_year=user.profile.birth_year,
            sex=user.profile.sex,
            diet_type=user.profile.diet_type,
            activity_level=user.profile.activity_level,
            age_years=user.profile.age_years,
            weight_value=user.profile.weight_value,
            weight_unit=user.profile.weight_unit,
            weight_kg=user.profile.weight_kg,
            height_value=user.profile.height_value,
            height_unit=user.profile.height_unit,
            height_cm=user.profile.height_cm,
            health_goals=user.profile.health_goals or {},
            allergies=user.profile.allergies or {},
            medical_warnings=user.profile.medical_warnings or {},
        )

    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        status=user.status,
        roles=user_roles(user),
        profile=profile,
        personal_info=to_personal_info_out(user.personal_info),
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


class UserService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = UserRepository(db)

    def create_user(self, *, email: str, password: str, display_name: str | None = None) -> UserOut:
        try:
            user = self.repo.create_user(email=email, password=password, display_name=display_name)
        except IntegrityError as exc:
            self.db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El email ya está registrado.") from exc
        return to_user_out(user)

    def get_user(self, user_id: UUID | str) -> UserOut:
        user = self.repo.get_by_id(user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")
        return to_user_out(user)

    def update_me(self, user: User, data: UserUpdate) -> UserOut:
        values = data.model_dump(exclude_unset=True)
        if "display_name" in values:
            user.display_name = values["display_name"]
        self.db.commit()
        refreshed = self.repo.get_by_id(user.id) or user
        return to_user_out(refreshed)

    def update_profile(self, user: User, data: UserProfileUpdate) -> UserProfileOut:
        profile = self.repo.update_profile(user, data.model_dump(exclude_unset=True))
        return UserProfileOut(
            birth_year=profile.birth_year,
            sex=profile.sex,
            diet_type=profile.diet_type,
            activity_level=profile.activity_level,
            age_years=profile.age_years,
            weight_value=profile.weight_value,
            weight_unit=profile.weight_unit,
            weight_kg=profile.weight_kg,
            height_value=profile.height_value,
            height_unit=profile.height_unit,
            height_cm=profile.height_cm,
            health_goals=profile.health_goals or {},
            allergies=profile.allergies or {},
            medical_warnings=profile.medical_warnings or {},
        )

    def get_personal_info(self, user: User) -> UserPersonalInfoOut:
        return to_personal_info_out(user.personal_info) or UserPersonalInfoOut()

    def update_personal_info(self, user: User, data: UserPersonalInfoUpdate) -> UserPersonalInfoOut:
        personal_info = self.repo.update_personal_info(user, data.model_dump(exclude_unset=True))
        return to_personal_info_out(personal_info) or UserPersonalInfoOut()

    def clear_personal_info(self, user: User) -> UserPersonalInfoOut:
        personal_info = self.repo.clear_personal_info(user)
        return to_personal_info_out(personal_info) or UserPersonalInfoOut()

    def export_health_data(self, user: User) -> UserHealthDataExportOut:
        refreshed = self.repo.get_by_id(user.id) or user
        lab_export = LabAnalysisService(self.db).export_user_health_data(refreshed)
        recommendation_rows = list(
            self.db.scalars(
                select(RecommendationSession)
                .where(RecommendationSession.user_id == refreshed.id)
                .order_by(RecommendationSession.created_at.desc())
                .limit(100)
            )
        )
        return UserHealthDataExportOut(
            exported_at=utcnow(),
            user_id=refreshed.id,
            profile=to_user_out(refreshed).profile,
            personal_info=to_personal_info_out(refreshed.personal_info),
            lab_reports=lab_export.get("reports", []),
            recommendation_profile_snapshots=[
                {
                    "id": row.id,
                    "recommendation_id": row.recommendation_id,
                    "created_at": row.created_at,
                    "input_payload": row.input_payload_json or {},
                    "conditions": row.conditions_json or {},
                    "profile_warnings": row.profile_warnings_json or [],
                    "model_versions": row.model_versions_json or {},
                }
                for row in recommendation_rows
            ],
        )

    def delete_health_data(self, user: User) -> UserHealthDataDeleteOut:
        labs_deleted = LabAnalysisService(self.db).delete_all_user_health_data(user)
        profile = user.profile
        cleared = False
        if profile is not None:
            profile.birth_year = None
            profile.sex = None
            profile.diet_type = None
            profile.activity_level = None
            profile.age_years = None
            profile.weight_value = None
            profile.weight_unit = None
            profile.weight_kg = None
            profile.height_value = None
            profile.height_unit = None
            profile.height_cm = None
            profile.health_goals = {}
            profile.allergies = {}
            profile.medical_warnings = {}
            self.db.commit()
            cleared = True
        return UserHealthDataDeleteOut(
            message="Datos de salud eliminados o anonimizados.",
            lab_reports_deleted=labs_deleted,
            profile_health_fields_cleared=cleared,
        )

    def list_users(self, limit: int = 100, offset: int = 0) -> list[UserOut]:
        return [to_user_out(user) for user in self.repo.list_users(limit=limit, offset=offset)]
