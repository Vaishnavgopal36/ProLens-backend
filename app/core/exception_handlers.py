import logging
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from http import HTTPStatus

from app.core.exception import AppException

logger = logging.getLogger("app")


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status_code": exc.status_code,
            "status_message": exc.message,
            "error_message": exc.details or exc.message,
            "response_data": None,
        },
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    status_phrase = HTTPStatus(exc.status_code).phrase  # e.g. "Unauthorized"
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status_code": exc.status_code,
            "status_message": status_phrase,  # "Unauthorized"
            "error_message": str(exc.detail),  # "Could not validate credentials"
            "response_data": None,
        },
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "status_code": status.HTTP_422_UNPROCESSABLE_ENTITY,
            "status_message": "Validation Error",
            "error_message": exc.errors(),
            "response_data": None,
        },
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled server exception: %s", str(exc))
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
            "status_message": "Internal Server Error",
            "error_message": "An unexpected error occurred. Please try again later.",
            "response_data": None,
        },
    )
