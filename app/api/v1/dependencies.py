from collections.abc import Generator

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.models import User
from app.db.session import get_db
from app.domains.users.repositorio_usuarios import UserRepository, user_roles


def db_session() -> Generator[Session, None, None]:
    yield from get_db()


def current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(db_session),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token requerido.")

    token = authorization.split(" ", 1)[1].strip()
    payload = decode_access_token(token)
    if payload is None or not payload.get("sub"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido.")

    user = UserRepository(db).get_by_id(payload["sub"])
    if user is None or user.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario inválido.")

    return user


def optional_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(db_session),
) -> User | None:
    if not authorization:
        return None
    return current_user(authorization=authorization, db=db)


def require_admin(user: User = Depends(current_user)) -> User:
    roles = set(user_roles(user))
    if "admin" not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Rol admin requerido.")
    return user


def require_moderator_or_admin(user: User = Depends(current_user)) -> User:
    roles = set(user_roles(user))
    if not {"moderator", "admin"}.intersection(roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Rol moderator/admin requerido.")
    return user
