from __future__ import annotations

import hashlib
import secrets
import smtplib
from datetime import timedelta
from email.message import EmailMessage

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.observability import log_event
from app.core.security import create_access_token
from app.core.security import verify_password
from app.db.models import PasswordResetToken, RefreshToken, User, utcnow
from app.repositories.user_repository import UserRepository, user_roles
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
from app.services.user_service import UserService, to_user_out


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


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
        refresh_token = self._create_refresh_token(user_id=user_out.id)
        log_event("user_registered", user_id=str(user_out.id), roles=user_out.roles)
        return TokenResponse(access_token=token, refresh_token=refresh_token, user=user_out)

    def login(self, data: LoginInput) -> TokenResponse:
        user = self.repo.authenticate(email=data.email, password=data.password)
        if user is None:
            log_event("login_failed", email_domain=data.email.split("@")[-1] if "@" in data.email else "invalid")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas.")

        roles = user_roles(user)
        token = create_access_token(str(user.id), {"roles": roles})
        refresh_token = self._create_refresh_token(user_id=user.id)
        log_event("login_succeeded", user_id=str(user.id), roles=roles)
        return TokenResponse(access_token=token, refresh_token=refresh_token, user=to_user_out(user))

    def refresh(self, data: RefreshTokenInput) -> TokenResponse:
        now = utcnow()
        record = self.db.scalar(
            select(RefreshToken)
            .where(
                RefreshToken.token_hash == _token_hash(data.refresh_token),
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at >= now,
            )
            .limit(1)
        )
        if record is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token inválido o expirado.")

        user = self.db.get(User, record.user_id)
        if user is None or user.status != "active":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario inválido.")

        loaded_user = self.repo.get_by_id(user.id) or user
        roles = user_roles(loaded_user)
        access_token = create_access_token(str(user.id), {"roles": roles})
        new_refresh_token = self._create_refresh_token(user_id=user.id, commit=False)
        replacement = self.db.scalar(
            select(RefreshToken)
            .where(RefreshToken.token_hash == _token_hash(new_refresh_token))
            .limit(1)
        )
        record.revoked_at = now
        if replacement is not None:
            record.replaced_by_token_id = replacement.id
        self.db.commit()
        log_event("refresh_token_rotated", user_id=str(user.id))
        return TokenResponse(access_token=access_token, refresh_token=new_refresh_token, user=to_user_out(loaded_user))

    def logout(self, data: RefreshTokenInput) -> MessageOut:
        record = self.db.scalar(
            select(RefreshToken)
            .where(RefreshToken.token_hash == _token_hash(data.refresh_token), RefreshToken.revoked_at.is_(None))
            .limit(1)
        )
        if record is not None:
            record.revoked_at = utcnow()
            self.db.commit()
            log_event("refresh_token_revoked", user_id=str(record.user_id))
        return MessageOut(message="Sesión cerrada.")

    def logout_all(self, user: User) -> MessageOut:
        count = self._revoke_all_refresh_tokens(user)
        log_event("refresh_tokens_revoked_all", user_id=str(user.id), count=count)
        return MessageOut(message="Sesiones cerradas.")

    def request_password_reset(
        self,
        data: PasswordForgotInput,
        *,
        requested_ip: str | None = None,
        user_agent: str | None = None,
    ) -> PasswordResetRequestOut:
        user = self.repo.get_by_email(data.email)
        reset_token: str | None = None
        if user is not None and user.status == "active":
            token = secrets.token_urlsafe(48)
            record = PasswordResetToken(
                user_id=user.id,
                token_hash=_token_hash(token),
                expires_at=utcnow() + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_TTL_MINUTES),
                requested_ip=requested_ip,
                user_agent=(user_agent or "")[:1000] or None,
            )
            self.db.add(record)
            self.db.commit()
            self._send_password_reset_email(user, token)
            reset_token = token if settings.PASSWORD_RESET_RETURN_TOKEN else None
            log_event("password_reset_requested", user_id=str(user.id), returned_for_demo=bool(reset_token))
        else:
            log_event("password_reset_requested_unknown_email", email_domain=data.email.split("@")[-1] if "@" in data.email else "invalid")

        return PasswordResetRequestOut(
            message="Si el correo existe, se generó una instrucción de recuperación.",
            reset_token=reset_token,
        )

    def reset_password(self, data: PasswordResetInput) -> MessageOut:
        now = utcnow()
        record = self.db.scalar(
            select(PasswordResetToken)
            .where(
                PasswordResetToken.token_hash == _token_hash(data.token),
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.expires_at >= now,
            )
            .limit(1)
        )
        if record is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token inválido o expirado.")

        user = self.db.get(User, record.user_id)
        if user is None or user.status != "active":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuario inválido.")

        self.repo.update_password(user, data.new_password)
        record.used_at = now
        self._revoke_all_refresh_tokens(user, commit=False)
        self.db.commit()
        log_event("password_reset_completed", user_id=str(user.id))
        return MessageOut(message="Contraseña actualizada.")

    def _send_password_reset_email(self, user: User, token: str) -> None:
        if not settings.SMTP_HOST or not settings.SMTP_FROM_EMAIL:
            log_event("password_reset_email_skipped", user_id=str(user.id), reason="smtp_not_configured")
            return

        reset_url = f"{settings.PUBLIC_FRONTEND_URL.rstrip('/')}/?reset_token={token}"
        message = EmailMessage()
        message["Subject"] = "Recupera tu contraseña de SupleMatch"
        message["From"] = settings.SMTP_FROM_EMAIL
        message["To"] = user.email
        message.set_content(
            "\n".join(
                [
                    "Solicitaste recuperar tu contraseña de SupleMatch.",
                    "",
                    f"Abre este enlace y pega el token si la app lo solicita: {reset_url}",
                    "",
                    f"Token: {token}",
                    "",
                    f"El token expira en {settings.PASSWORD_RESET_TOKEN_TTL_MINUTES} minutos.",
                    "Si no solicitaste este cambio, ignora este mensaje.",
                ]
            )
        )
        try:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
                if settings.SMTP_USE_TLS:
                    smtp.starttls()
                if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                    smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                smtp.send_message(message)
            log_event("password_reset_email_sent", user_id=str(user.id))
        except Exception as exc:
            log_event("password_reset_email_failed", user_id=str(user.id), error=str(exc)[:200])

    def change_password(self, user: User, data: PasswordChangeInput) -> MessageOut:
        if not verify_password(data.current_password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Contraseña actual inválida.")
        self.repo.update_password(user, data.new_password)
        self._revoke_all_refresh_tokens(user)
        log_event("password_changed", user_id=str(user.id))
        return MessageOut(message="Contraseña actualizada.")

    def _create_refresh_token(self, *, user_id, commit: bool = True) -> str:
        token = secrets.token_urlsafe(48)
        record = RefreshToken(
            user_id=user_id,
            token_hash=_token_hash(token),
            expires_at=utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
        self.db.add(record)
        self.db.flush()
        if commit:
            self.db.commit()
        return token

    def _revoke_all_refresh_tokens(self, user: User, *, commit: bool = True) -> int:
        now = utcnow()
        tokens = list(
            self.db.scalars(
                select(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            )
        )
        for token in tokens:
            token.revoked_at = now
        if commit:
            self.db.commit()
        return len(tokens)
