from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.security import hash_password, verify_password
from app.db.models import Role, User, UserPersonalInfo, UserProfile, UserRole, utcnow


BASE_ROLE = "user"


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, user_id: UUID | str) -> User | None:
        try:
            parsed_user_id = user_id if isinstance(user_id, UUID) else UUID(str(user_id))
        except ValueError:
            return None

        return self.db.scalar(
            select(User)
            .options(
                selectinload(User.roles).selectinload(UserRole.role),
                selectinload(User.profile),
                selectinload(User.personal_info),
            )
            .where(User.id == parsed_user_id)
        )

    def get_by_email(self, email: str) -> User | None:
        return self.db.scalar(
            select(User)
            .options(
                selectinload(User.roles).selectinload(UserRole.role),
                selectinload(User.profile),
                selectinload(User.personal_info),
            )
            .where(User.email == email.lower().strip())
        )

    def create_user(self, *, email: str, password: str, display_name: str | None = None) -> User:
        user = User(
            email=email.lower().strip(),
            password_hash=hash_password(password),
            display_name=display_name,
            status="active",
        )
        self.db.add(user)
        self.db.flush()
        self.assign_role(user, BASE_ROLE)
        self.db.commit()
        self.db.refresh(user)
        return self.get_by_id(user.id) or user

    def authenticate(self, *, email: str, password: str) -> User | None:
        user = self.get_by_email(email)
        if user is None or user.status != "active":
            return None
        if not verify_password(password, user.password_hash):
            return None
        user.last_login_at = utcnow()
        self.db.commit()
        return self.get_by_id(user.id)

    def update_password(self, user: User, password: str) -> User:
        user.password_hash = hash_password(password)
        user.updated_at = utcnow()
        self.db.commit()
        self.db.refresh(user)
        return user

    def assign_role(self, user: User, role_name: str) -> None:
        role = self.db.scalar(select(Role).where(Role.name == role_name))
        if role is None:
            role = Role(name=role_name, description=f"Rol {role_name}")
            self.db.add(role)
            self.db.flush()

        has_role = any(item.role_id == role.id for item in user.roles)
        if not has_role:
            self.db.add(UserRole(user_id=user.id, role_id=role.id))
            self.db.flush()

    def update_profile(self, user: User, values: dict) -> UserProfile:
        profile = user.profile
        if profile is None:
            profile = UserProfile(user_id=user.id)
            self.db.add(profile)
            self.db.flush()

        for key, value in values.items():
            if value is not None and hasattr(profile, key):
                setattr(profile, key, value)

        self.db.commit()
        self.db.refresh(profile)
        return profile

    def update_personal_info(self, user: User, values: dict) -> UserPersonalInfo:
        personal_info = user.personal_info
        if personal_info is None:
            personal_info = UserPersonalInfo(user_id=user.id)
            self.db.add(personal_info)
            self.db.flush()

        for key, value in values.items():
            if key == "preferences":
                personal_info.preferences_json = value or {}
            elif hasattr(personal_info, key):
                setattr(personal_info, key, value)

        self.db.commit()
        self.db.refresh(personal_info)
        return personal_info

    def clear_personal_info(self, user: User) -> UserPersonalInfo:
        personal_info = user.personal_info
        if personal_info is None:
            personal_info = UserPersonalInfo(user_id=user.id)
            self.db.add(personal_info)
            self.db.flush()

        personal_info.first_name = None
        personal_info.last_name = None
        personal_info.phone = None
        personal_info.country = None
        personal_info.city = None
        personal_info.district = None
        personal_info.address_line = None
        personal_info.date_of_birth = None
        personal_info.document_type = None
        personal_info.document_number = None
        personal_info.preferences_json = {}
        personal_info.updated_at = utcnow()
        self.db.commit()
        self.db.refresh(personal_info)
        return personal_info

    def list_users(self, limit: int = 100, offset: int = 0) -> list[User]:
        return list(
            self.db.scalars(
                select(User)
                .options(
                    selectinload(User.roles).selectinload(UserRole.role),
                    selectinload(User.profile),
                    selectinload(User.personal_info),
                )
                .order_by(User.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
        )


def user_roles(user: User) -> list[str]:
    return sorted(item.role.name for item in user.roles if item.role)
