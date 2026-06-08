from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import User
from app.repositories.user_repository import UserRepository, user_roles
from app.schemas.user import UserOut, UserProfileOut, UserProfileUpdate, UserUpdate


def to_user_out(user: User) -> UserOut:
    profile = None
    if user.profile is not None:
        profile = UserProfileOut(
            birth_year=user.profile.birth_year,
            sex=user.profile.sex,
            diet_type=user.profile.diet_type,
            activity_level=user.profile.activity_level,
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
            health_goals=profile.health_goals or {},
            allergies=profile.allergies or {},
            medical_warnings=profile.medical_warnings or {},
        )

    def list_users(self, limit: int = 100, offset: int = 0) -> list[UserOut]:
        return [to_user_out(user) for user in self.repo.list_users(limit=limit, offset=offset)]
