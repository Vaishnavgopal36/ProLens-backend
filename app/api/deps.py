import uuid
from collections.abc import Callable

import jwt
from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exception import (
    CrossOrganizationForbiddenError,
    InsufficientPermissionError,
    InvalidCredentialsAuthError,
)
from app.core.security import decode_access_token
from app.models.enums import UserRole
from app.models.tenancy import Organization
from app.models.user import User
from app.services.auth_service import is_account_usable


def bypass_rls_for_pre_auth_lookup(db: Session) -> None:
    db.execute(text("SET LOCAL app.is_super_admin = 'true'"))


def authenticate_access_token(token: str | None, db: Session) -> tuple[User, dict]:
    """Validate an access-token JWT and load its user, setting RLS session vars.

    Shared by the REST dependency and the WebSocket handshake. Returns the user
    and the decoded token payload (callers may need ``exp``).
    """
    if token is None:
        raise InvalidCredentialsAuthError()

    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        raise InvalidCredentialsAuthError()

    db.execute(
        text("SET LOCAL app.current_user_id = :user_id"), {"user_id": str(user_id)}
    )

    user = db.get(User, user_id)
    if user is None:
        raise InvalidCredentialsAuthError()

    db.execute(
        text("SET LOCAL app.current_org_id = :org_id"),
        {"org_id": str(user.organization_id) if user.organization_id else ""},
    )
    db.execute(
        text("SET LOCAL app.is_super_admin = :is_super_admin"),
        {"is_super_admin": "true" if user.role == UserRole.super_admin else "false"},
    )

    # Loaded after the RLS context above so the org row is visible to its members.
    organization = (
        db.get(Organization, user.organization_id)
        if user.organization_id is not None
        else None
    )
    if not is_account_usable(user, organization):
        raise InvalidCredentialsAuthError()

    return user, payload


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    user, _ = authenticate_access_token(request.cookies.get("access_token"), db)
    return user


def require_roles(*roles: UserRole) -> Callable[..., User]:
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise InsufficientPermissionError()
        return user

    return dependency


def assert_same_organization(
    caller: User, resource_organization_id: uuid.UUID | None
) -> None:
    if (
        caller.role != UserRole.super_admin
        and resource_organization_id != caller.organization_id
    ):
        raise CrossOrganizationForbiddenError()
