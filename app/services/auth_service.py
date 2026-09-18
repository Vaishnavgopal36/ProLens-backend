from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    verify_password,
)
from app.models.enums import UserStatus
from app.models.session import UserSession
from app.models.user import User
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import TokenResponse
from app.services.exceptions import (
    InactiveAccountError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
)


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.users = UserRepository(db)
        self.sessions = SessionRepository(db)

    def issue_tokens(self, user: User) -> TokenResponse:
        refresh_token = generate_refresh_token()
        self.sessions.create(
            UserSession(
                user_id=user.id,
                refresh_token_hash=hash_refresh_token(refresh_token),
                expires_at=datetime.now(timezone.utc)
                + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            )
        )
        return TokenResponse(
            access_token=create_access_token(user.id, user.organization_id),
            refresh_token=refresh_token,
        )

    def login(self, email: str, password: str) -> TokenResponse:
        user = self.users.get_by_email(email)
        if (
            user is None
            or user.password_hash is None
            or not verify_password(password, user.password_hash)
        ):
            raise InvalidCredentialsError()

        if user.status != UserStatus.active:
            raise InactiveAccountError()

        return self.issue_tokens(user)

    def _get_active_session(self, refresh_token: str) -> UserSession | None:
        token_hash = hash_refresh_token(refresh_token)
        session = self.sessions.get_by_refresh_token_hash(token_hash)
        if session is None or session.revoked_at is not None:
            return None
        if session.expires_at < datetime.now(timezone.utc):
            return None
        return session

    def refresh(self, refresh_token: str) -> TokenResponse:
        session = self._get_active_session(refresh_token)
        if session is None:
            raise InvalidRefreshTokenError()

        user = self.users.get_by_id(session.user_id)
        if user is None or user.status != UserStatus.active:
            raise InvalidRefreshTokenError()

        session.revoked_at = datetime.now(timezone.utc)
        self.db.add(session)

        return self.issue_tokens(user)

    def logout(self, refresh_token: str) -> None:
        session = self._get_active_session(refresh_token)
        if session is not None:
            self.sessions.revoke(session)