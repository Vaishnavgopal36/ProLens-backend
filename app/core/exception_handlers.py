from http import HTTPStatus

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.schemas.common_response import APIResponse
from app.services.exceptions import (
    # CrossOrganizationForbiddenError,
    # EmailAlreadyExistsError,
    InactiveAccountError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    InvalidSSOStateError,
    MissingEmailClaimError,
    NoSSOConnectionError,
    # OrganizationIdRequiredError,
    # UserNotFoundError,
)

DOMAIN_EXCEPTION_MAP: dict[type[Exception], tuple[int, str]] = {
    InvalidCredentialsError: (401, "Incorrect email or password"),
    InactiveAccountError: (403, "Account is not active"),
    InvalidRefreshTokenError: (401, "Invalid or expired refresh token"),
    NoSSOConnectionError: (404, "No SSO connection configured for this organization"),
    InvalidSSOStateError: (400, "Invalid or expired SSO state"),
    MissingEmailClaimError: (400, "Identity provider did not return an email claim"),
    # EmailAlreadyExistsError: (409, "Email already in use"),
    # OrganizationIdRequiredError: (422, "organization_id is required"),
    # CrossOrganizationForbiddenError: (403, "Cannot create users outside your organization"),
    # UserNotFoundError: (404, "User not found"),
}


def domain_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    status_code, default_detail = DOMAIN_EXCEPTION_MAP[type(exc)]
    try:
        status_message = HTTPStatus(status_code).phrase
    except ValueError:
        status_message = "Request failed"

    response = APIResponse[None](
        status_code=status_code,
        status_message=status_message,
        error_message=str(exc) or default_detail,
        response_data=None,
    )
    return JSONResponse(
        status_code=status_code, content=response.model_dump(mode="json")
    )


# --- your existing handlers, unchanged ---


def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    try:
        status_message = HTTPStatus(exc.status_code).phrase
    except ValueError:
        status_message = "Request failed"

    response = APIResponse[None](
        status_code=exc.status_code,
        status_message=status_message,
        error_message=str(exc.detail),
        response_data=None,
    )
    return JSONResponse(
        status_code=exc.status_code, content=response.model_dump(mode="json")
    )


def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    messages = []
    for error in exc.errors():
        location = " -> ".join(str(item) for item in error["loc"])
        messages.append(f"{location}: {error['msg']}")

    response = APIResponse[None](
        status_code=422,
        status_message="Validation Error",
        error_message="; ".join(messages),
        response_data=None,
    )
    return JSONResponse(status_code=422, content=response.model_dump(mode="json"))


def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    response = APIResponse[None](
        status_code=500,
        status_message="Internal Server Error",
        error_message="An unexpected error occurred",
        response_data=None,
    )
    return JSONResponse(status_code=500, content=response.model_dump(mode="json"))
