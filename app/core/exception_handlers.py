import logging
from http import HTTPStatus

from fastapi import Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError, IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exception import AppException
from app.core.storage import StorageError

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


async def storage_exception_handler(
    request: Request, exc: StorageError
) -> JSONResponse:
    logger.error("Storage error: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={
            "status_code": status.HTTP_502_BAD_GATEWAY,
            "status_message": "Bad Gateway",
            "error_message": "File storage is unavailable",
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
            # ctx may hold the raw exception from a model_validator.
            "error_message": jsonable_encoder(
                exc.errors(), custom_encoder={Exception: str}
            ),
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


def _error(status_code: int, phrase: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "status_code": status_code,
            "status_message": phrase,
            "error_message": message,
            "response_data": None,
        },
    )


async def integrity_error_handler(
    request: Request, exc: IntegrityError
) -> JSONResponse:
    logger.warning("Integrity error: %s", exc.orig or exc)
    # Postgres SQLSTATE: 23505 unique, 23503 foreign key, 23502 not-null, 23514 check.
    sqlstate = getattr(exc.orig, "pgcode", None) or getattr(exc.orig, "sqlstate", None)
    if sqlstate == "23505":
        return _error(status.HTTP_409_CONFLICT, "Conflict", "Resource already exists")
    if sqlstate in ("23502", "23514"):
        return _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Unprocessable Entity",
            "Request violates a data constraint",
        )
    return _error(
        status.HTTP_409_CONFLICT,
        "Conflict",
        "Request conflicts with the current state of the resource",
    )


async def data_error_handler(request: Request, exc: DataError) -> JSONResponse:
    logger.warning("Data error: %s", exc.orig or exc)
    return _error(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "Unprocessable Entity",
        "Invalid data in request",
    )
