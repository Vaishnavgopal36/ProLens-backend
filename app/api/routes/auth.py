from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import bypass_rls_for_pre_auth_lookup, get_current_user
from app.core.config import settings
from app.core.cookies import clear_auth_cookies, set_auth_cookies
from app.core.database import get_db
from app.core.exception import (
    AppException,
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
        first_name=user.first_name,
        last_name=user.last_name,
        designation=user.designation.name if user.designation else None,
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

@router.get("/sso/callback")
def sso_callback(
    db: Session = Depends(get_db),
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> Response:
    if error or code is None or state is None:
        err_msg = error_description or error or "sso_cancelled"
        return RedirectResponse(
            url=f"{settings.FRONTEND_BASE_URL}/login?error=sso_failed&message={err_msg}",
            status_code=status.HTTP_302_FOUND,
        )

    bypass_rls_for_pre_auth_lookup(db)

    try:
        tokens = SSOService(db).callback(code, state)
        db.commit()
    except AppException as e:
        return RedirectResponse(
            url=f"{settings.FRONTEND_BASE_URL}/login?error=sso_failed&message={e.default_message}",
            status_code=status.HTTP_302_FOUND,
        )
    except Exception:
        return RedirectResponse(
            url=f"{settings.FRONTEND_BASE_URL}/login?error=sso_failed&message=Authentication failed",
            status_code=status.HTTP_302_FOUND,
        )

    if tokens is None:
        return RedirectResponse(
            url=f"{settings.FRONTEND_BASE_URL}/users?sso=connected",
            status_code=status.HTTP_302_FOUND,
        )

    redirect = RedirectResponse(
        url=f"{settings.FRONTEND_BASE_URL}/dashboard",
        status_code=status.HTTP_302_FOUND,
    )
    set_auth_cookies(redirect, tokens)
    return redirect