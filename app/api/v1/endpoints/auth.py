from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.dependencies import current_user, db_session
from app.db.models import User
from app.schemas.auth import LoginInput, RegisterInput, TokenResponse
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


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return to_user_out(user)
