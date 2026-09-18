from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    status_code: int
    status_message: str
    error_message: str | dict | None = None
    response_data: T | None = None


def success_response(
    *,
    status_code: int,
    status_message: str,
    response_data: T | None = None,
) -> APIResponse[T]:
    return APIResponse(
        status_code=status_code,
        status_message=status_message,
        error_message=None,
        response_data=response_data,
    )


COMMON_RESPONSES = {
    422: {
        "model": APIResponse[None],
        "description": "Validation Error",
    },
}
