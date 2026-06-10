from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.v1.dependencies import current_user, db_session
from app.db.models import User
from app.schemas.auth import (
    LoginInput,
    MessageOut,
    PasswordChangeInput,
    PasswordForgotInput,
    RefreshTokenInput,
    PasswordResetInput,
    PasswordResetRequestOut,
    RegisterInput,
    TokenResponse,
)
from app.schemas.user import UserOut
from app.services.auth_service import AuthService
from app.services.user_service import to_user_out


router = APIRouter()


@router.post("/register", response_model=TokenResponse)
def register(data: RegisterInput, db: Session = Depends(db_session)):
    return AuthService(db).register(data)


@router.post("/login", response_model=TokenResponse)
def login(data: LoginInput, db: Session = Depends(db_session)):
    return AuthService(db).login(data)


@router.post("/refresh", response_model=TokenResponse)
def refresh(data: RefreshTokenInput, db: Session = Depends(db_session)):
    return AuthService(db).refresh(data)


@router.post("/logout", response_model=MessageOut)
def logout(data: RefreshTokenInput, db: Session = Depends(db_session)):
    return AuthService(db).logout(data)


@router.post("/logout-all", response_model=MessageOut)
def logout_all(user: User = Depends(current_user), db: Session = Depends(db_session)):
    return AuthService(db).logout_all(user)


@router.post("/forgot-password", response_model=PasswordResetRequestOut)
def forgot_password(data: PasswordForgotInput, request: Request, db: Session = Depends(db_session)):
    return AuthService(db).request_password_reset(
        data,
        requested_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@router.post("/reset-password", response_model=MessageOut)
def reset_password(data: PasswordResetInput, db: Session = Depends(db_session)):
    return AuthService(db).reset_password(data)


@router.post("/change-password", response_model=MessageOut)
def change_password(
    data: PasswordChangeInput,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    return AuthService(db).change_password(user, data)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return to_user_out(user)
