from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.dependencies import current_user, db_session, require_admin
from app.db.models import User
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
from app.domains.users.servicio_usuarios import UserService, to_user_out


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


@router.get("/me/personal", response_model=UserPersonalInfoOut)
def get_my_personal_info(
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    return UserService(db).get_personal_info(user)


@router.put("/me/personal", response_model=UserPersonalInfoOut)
def update_my_personal_info(
    data: UserPersonalInfoUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    return UserService(db).update_personal_info(user, data)


@router.delete("/me/personal", response_model=UserPersonalInfoOut)
def clear_my_personal_info(
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    return UserService(db).clear_personal_info(user)


@router.get("/me/health-data/export", response_model=UserHealthDataExportOut)
def export_my_health_data(
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    return UserService(db).export_health_data(user)


@router.delete("/me/health-data", response_model=UserHealthDataDeleteOut)
def delete_my_health_data(
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    return UserService(db).delete_health_data(user)


@router.get("", response_model=list[UserOut])
def list_users(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
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
