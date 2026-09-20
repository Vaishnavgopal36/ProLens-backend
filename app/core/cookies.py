from fastapi import Response

from app.core.config import settings
from app.schemas.auth import TokenResponse


def set_auth_cookies(response: Response, tokens: TokenResponse) -> None:
    response.set_cookie(
        key="access_token",
        value=tokens.access_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=3600,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=tokens.refresh_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=86400 * settings.REFRESH_TOKEN_EXPIRE_DAYS,
        path="/auth/refresh",
    )