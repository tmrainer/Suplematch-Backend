from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.dependencies import current_user, db_session, require_admin
from app.db.models import User
from app.schemas.user import UserOut, UserProfileOut, UserProfileUpdate, UserUpdate
from app.services.user_service import UserService, to_user_out


router = APIRouter()


@router.get("/me", response_model=UserOut)
def get_me(user: User = Depends(current_user)):
    return to_user_out(user)


@router.patch("/me", response_model=UserOut)
def update_me(
    data: UserUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    return UserService(db).update_me(user, data)


@router.put("/me/profile", response_model=UserProfileOut)
def update_my_profile(
    data: UserProfileUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    return UserService(db).update_profile(user, data)


@router.get("", response_model=list[UserOut])
def list_users(
    limit: int = 100,
    offset: int = 0,
    _admin: User = Depends(require_admin),
    db: Session = Depends(db_session),
):
    return UserService(db).list_users(limit=limit, offset=offset)


@router.get("/{user_id}", response_model=UserOut)
def get_user(
    user_id: str,
    _admin: User = Depends(require_admin),
    db: Session = Depends(db_session),
):
    return UserService(db).get_user(user_id)
