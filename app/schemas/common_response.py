from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    status_code: int
    status_message: str
    error_message: str | dict | list[Any] | None = None
    response_data: T | None = None


def success_response(
    *,
    status_code: int = 200,
    status_message: str = "Success",
    response_data: T | None = None,
) -> APIResponse[T]:
    return APIResponse(
        status_code=status_code,
        status_message=status_message,
        error_message=None,
        response_data=response_data,
    )


def error_response(
    *,
    status_code: int,
    status_message: str,
    error_message: str | dict | list[Any] | None = None,
) -> APIResponse[None]:
    return APIResponse(
        status_code=status_code,
        status_message=status_message,
        error_message=error_message,
        response_data=None,
    )
