from fastapi import APIRouter, Depends, HTTPException, Request, status, Response
from sqlalchemy.orm import Session
from app.core.config import settings
from app.api.deps import bypass_rls_for_pre_auth_lookup, get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.auth import (
    CurrentUser,
    LoginRequest,
    RefreshRequest,
    SSOAuthorizeResponse,
    TokenResponse,
)
from app.services.auth_service import AuthService
from app.services.exceptions import (
    InactiveAccountError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    InvalidSSOStateError,
    MissingEmailClaimError,
    NoSSOConnectionError,
)
from app.services.sso_service import SSOService
from app.schemas.common_response import APIResponse, success_response, COMMON_RESPONSES

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
    responses=COMMON_RESPONSES,
)


@router.post(
    "/login",
    response_model=APIResponse[TokenResponse],
)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> APIResponse[TokenResponse]:
    bypass_rls_for_pre_auth_lookup(db)
    try:
        tokens = AuthService(db).login(payload.email, payload.password)
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    except InactiveAccountError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active",
        )

    response.set_cookie(
        key="access_token",
        value=tokens.access_token,
        httponly=True,
        secure=True,           
        samesite="lax",       
        max_age=60 * 60,     
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=tokens.refresh_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 24 * settings.REFRESH_TOKEN_EXPIRE_DAYS,
        path="/auth/refresh",   
        
    )

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Login successful",
        response_data=None,   
    )


@router.post(
    "/refresh",
    response_model=APIResponse[TokenResponse],
)
def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> APIResponse[TokenResponse]:
    refresh_token = request.cookies.get("refresh_token")   
    if refresh_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )    
    bypass_rls_for_pre_auth_lookup(db)
    try:
        tokens = AuthService(db).refresh(refresh_token)
    except InvalidRefreshTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    response.set_cookie(
        key="access_token",
        value=tokens.access_token,
        httponly=True,
        secure=True,           
        samesite="lax",       
        max_age=60 * 60,     
        path="/",
        )
    response.set_cookie(
        key="refresh_token",
        value=tokens.refresh_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 24 * settings.REFRESH_TOKEN_EXPIRE_DAYS,
        path="/auth/refresh",   
        )
    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Token refreshed successfully",
        response_data=None,
    )


@router.post(
    "/logout",
    response_model=APIResponse[None],
    status_code=status.HTTP_200_OK,
)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> APIResponse[None]:
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        bypass_rls_for_pre_auth_lookup(db)
        AuthService(db).logout(refresh_token)

    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/auth/refresh")
    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Logout successful",
        response_data=None,
    )


@router.get(
    "/me",
    response_model=APIResponse[CurrentUser],
)
def me(
    user: User = Depends(get_current_user),
) -> APIResponse[CurrentUser]:
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


@router.get(
    "/sso/authorize",
    response_model=APIResponse[SSOAuthorizeResponse],
)
def sso_authorize(
    request: Request,
    db: Session = Depends(get_db),
) -> APIResponse[SSOAuthorizeResponse]:
    host = request.headers.get("host", "").split(":")[0].lower()
    bypass_rls_for_pre_auth_lookup(db)
    try:
        result = SSOService(db).authorize(host)
    except NoSSOConnectionError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No SSO connection configured for this organization",
        )

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="SSO authorization URL generated",
        response_data=result,
    )


@router.get(
    "/sso/callback",
    response_model=APIResponse[TokenResponse],
)
def sso_callback(
    code: str,
    state: str,
    db: Session = Depends(get_db),
) -> APIResponse[TokenResponse]:
    bypass_rls_for_pre_auth_lookup(db)
    try:
        tokens = SSOService(db).callback(code, state)
    except InvalidSSOStateError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired SSO state",
        )
    except NoSSOConnectionError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SSO connection not found",
        )
    except MissingEmailClaimError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Identity provider did not return an email claim",
        )
    except InactiveAccountError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active",
        )

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="SSO login successful",
        response_data=tokens,
    )