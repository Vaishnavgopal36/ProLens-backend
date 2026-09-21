from fastapi import Response

from app.core.config import settings
from app.schemas.auth import TokenResponse

ACCESS_COOKIE_PATH = "/"
# Scoped to /auth so both /auth/refresh and /auth/logout receive it.
REFRESH_COOKIE_PATH = "/auth"
# Older clients hold a refresh cookie scoped to this path; clear it on logout.
LEGACY_REFRESH_COOKIE_PATH = "/auth/refresh"


def set_auth_cookies(response: Response, tokens: TokenResponse) -> None:
    response.set_cookie(
        key="access_token",
        value=tokens.access_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        path=ACCESS_COOKIE_PATH,
    )
    response.set_cookie(
        key="refresh_token",
        value=tokens.refresh_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=86400 * settings.REFRESH_TOKEN_EXPIRE_DAYS,
        path=REFRESH_COOKIE_PATH,
    )
    # Drop a stale cookie from the old, narrower path so it cannot shadow this one.
    response.delete_cookie("refresh_token", path=LEGACY_REFRESH_COOKIE_PATH)


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path=ACCESS_COOKIE_PATH)
    response.delete_cookie("refresh_token", path=REFRESH_COOKIE_PATH)
    response.delete_cookie("refresh_token", path=LEGACY_REFRESH_COOKIE_PATH)
