from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.repositories.user_repository import UserRepository, user_roles
from app.schemas.auth import LoginInput, RegisterInput, TokenResponse
from app.services.user_service import UserService, to_user_out


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = UserRepository(db)

    def register(self, data: RegisterInput) -> TokenResponse:
        user_out = UserService(self.db).create_user(
            email=data.email,
            password=data.password,
            display_name=data.display_name,
        )
        token = create_access_token(str(user_out.id), {"roles": user_out.roles})
        return TokenResponse(access_token=token, user=user_out)

    def login(self, data: LoginInput) -> TokenResponse:
        user = self.repo.authenticate(email=data.email, password=data.password)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas.")

        roles = user_roles(user)
        token = create_access_token(str(user.id), {"roles": roles})
        return TokenResponse(access_token=token, user=to_user_out(user))
