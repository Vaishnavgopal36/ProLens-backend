from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exception import (
    InactiveAccountError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
)
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    verify_dummy_password,
    verify_password,
)
from app.models.enums import OrgStatus, UserStatus
from app.models.session import UserSession
from app.models.tenancy import Organization
from app.models.user import User
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import TokenResponse


def is_account_usable(user: User, organization: Organization | None) -> bool:
    """False for deleted/non-active users and for users of a deleted/suspended org.

    A user without an organization (super_admin) is only checked on its own status.
    Suspending or deleting an organization needs no session sweep: every request
    goes through this check (via get_current_user), so its users are locked out
    immediately and cannot refresh either.
    """
    if user.deleted_at is not None or user.status != UserStatus.active:
        return False
    if user.organization_id is None:
        return True
    return (
        organization is not None
        and organization.deleted_at is None
        and organization.status != OrgStatus.suspended
    )


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.users = UserRepository(db)
        self.sessions = SessionRepository(db)

    def _is_usable(self, user: User) -> bool:
        organization = (
            self.db.get(Organization, user.organization_id)
            if user.organization_id is not None
            else None
        )
        return is_account_usable(user, organization)

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
        user = self.users.get_by_email(email.strip().lower())

        if user is None or user.password_hash is None:
            # Same bcrypt cost whether or not the account exists (no user enumeration).
            verify_dummy_password(password)
            raise InvalidCredentialsError()
        if not verify_password(password, user.password_hash):
            raise InvalidCredentialsError()

        if user.deleted_at is not None:
            raise InvalidCredentialsError()
        if not self._is_usable(user):
            raise InactiveAccountError()

        return self.issue_tokens(user)

    def _get_active_session(
        self, refresh_token: str, *, for_update: bool = False
    ) -> UserSession | None:
        token_hash = hash_refresh_token(refresh_token)
        session = self.sessions.get_by_refresh_token_hash(
            token_hash, for_update=for_update
        )
        if session is None or session.revoked_at is not None:
            return None
        if session.expires_at < datetime.now(timezone.utc):
            return None
        return session

    def refresh(self, refresh_token: str) -> TokenResponse:
        session = self._get_active_session(refresh_token, for_update=True)
        if session is None:
            raise InvalidRefreshTokenError()

        user = self.users.get_by_id(session.user_id)
        if user is None or not self._is_usable(user):
            self.sessions.revoke(session)
            raise InvalidRefreshTokenError()

        self.sessions.revoke(session)
        return self.issue_tokens(user)

    def logout(self, refresh_token: str) -> None:
        session = self._get_active_session(refresh_token)
        if session is not None:
            self.sessions.revoke(session)
