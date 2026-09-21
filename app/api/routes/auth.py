from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import bypass_rls_for_pre_auth_lookup, get_current_user
from app.core.cookies import clear_auth_cookies, set_auth_cookies
from app.core.database import get_db
from app.core.exception import (
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    InvalidSSOStateError,
)
from app.core.rate_limit import login_rate_limiter
from app.models.user import User
from app.schemas.auth import CurrentUser, LoginRequest, SSOAuthorizeResponse
from app.schemas.common_response import APIResponse, success_response
from app.services.auth_service import AuthService
from app.services.sso_service import SSOService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=APIResponse[None])
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> APIResponse[None]:
    client_ip = request.client.host if request.client else "unknown"
    rate_key = f"{client_ip}:{payload.email}"
    login_rate_limiter.check(rate_key)

    bypass_rls_for_pre_auth_lookup(db)
    try:
        tokens = AuthService(db).login(payload.email, payload.password)
    except InvalidCredentialsError:
        login_rate_limiter.record(rate_key)
        raise
    login_rate_limiter.reset(rate_key)
    db.commit()
    set_auth_cookies(response, tokens)

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Login successful",
        response_data=None,
    )


@router.post("/refresh", response_model=APIResponse[None])
def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> APIResponse[None]:
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise InvalidRefreshTokenError()

    bypass_rls_for_pre_auth_lookup(db)
    try:
        tokens = AuthService(db).refresh(refresh_token)
    except InvalidRefreshTokenError:
        # Persist a revocation done for a deleted/suspended account before failing.
        db.commit()
        raise
    db.commit()
    set_auth_cookies(response, tokens)

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Token refreshed successfully",
        response_data=None,
    )


@router.post("/logout", response_model=APIResponse[None])
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> APIResponse[None]:
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        bypass_rls_for_pre_auth_lookup(db)
        AuthService(db).logout(refresh_token)
        db.commit()

    clear_auth_cookies(response)

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Logout successful",
    )


@router.get("/me", response_model=APIResponse[CurrentUser])
def me(user: User = Depends(get_current_user)) -> APIResponse[CurrentUser]:
    current_user = CurrentUser(
        id=user.id,
        organization_id=user.organization_id,
        email=user.email,
        role=user.role,
    )
    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Current user retrieved successfully",
        response_data=current_user,
    )


@router.get("/sso/authorize", response_model=APIResponse[SSOAuthorizeResponse])
def sso_authorize(
    request: Request,
    db: Session = Depends(get_db),
) -> APIResponse[SSOAuthorizeResponse]:
    host = request.headers.get("host", "").split(":")[0].lower()
    bypass_rls_for_pre_auth_lookup(db)

    result = SSOService(db).authorize(host)

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="SSO authorization URL generated",
        response_data=result,
    )


@router.get("/sso/callback", response_model=APIResponse[None])
def sso_callback(
    response: Response,
    db: Session = Depends(get_db),
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> APIResponse[None]:
    if error or code is None or state is None:
        raise InvalidSSOStateError()

    bypass_rls_for_pre_auth_lookup(db)

    tokens = SSOService(db).callback(code, state)
    db.commit()
    set_auth_cookies(response, tokens)

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="SSO login successful",
        response_data=None,
    )
