import uuid

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.enums import UserRole, UserStatus
from app.models.user import User

def bypass_rls_for_pre_auth_lookup(db: Session) -> None:
    db.execute(text("SET LOCAL app.is_super_admin = 'true'"))


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = request.cookies.get("access_token")
    if token is None:
        raise credentials_error
    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise credentials_error

    db.execute(
        text("SET LOCAL app.current_user_id = :user_id"), {"user_id": str(user_id)}
    )

    user = db.get(User, user_id)
    if user is None or user.status != UserStatus.active:
        raise credentials_error

    db.execute(
        text("SET LOCAL app.current_org_id = :org_id"),
        {"org_id": str(user.organization_id) if user.organization_id else ""},
    )
    db.execute(
        text("SET LOCAL app.is_super_admin = :is_super_admin"),
        {"is_super_admin": "true" if user.role == UserRole.super_admin else "false"},
    )

    return user


def require_roles(*roles):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return dependency
