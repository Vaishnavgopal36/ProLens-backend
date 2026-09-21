import functools
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:  # malformed hash, or password longer than bcrypt's 72 bytes
        return False


@functools.lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return hash_password("prolens-dummy-password")


def verify_dummy_password(password: str) -> None:
    """Burn the same bcrypt time as a real check (unknown-user login path)."""
    verify_password(password, _dummy_hash())


def create_access_token(user_id: uuid.UUID, organization_id: uuid.UUID | None) -> str:
    payload = {
        "sub": str(user_id),
        "org_id": str(organization_id) if organization_id else None,
        "exp": datetime.now(timezone.utc)
        + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def decode_access_token(token: str) -> dict:
    return jwt.decode(
        token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
    )


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(64)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
