import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.pagination import Pagination, get_pagination
from app.core.database import get_db
from app.models.enums import LeaveType
from app.models.user import User
from app.schemas.common_response import (
    APIResponse,
    success_response,
)
from app.schemas.leave_log import (
    LeaveLogCreate,
    LeaveLogRead,
    LeaveLogUpdate,
)
from app.services.leave_log_service import LeaveLogService

router = APIRouter(
    prefix="/leave-logs",
    tags=["leave-logs"],
)


def get_leave_log_service(db: Session = Depends(get_db)) -> LeaveLogService:
    return LeaveLogService(db)


@router.post(
    "",
    response_model=APIResponse[LeaveLogRead],
    status_code=http_status.HTTP_201_CREATED,
)
def create_leave_log(
    payload: LeaveLogCreate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
    service: LeaveLogService = Depends(get_leave_log_service),
) -> APIResponse[LeaveLogRead]:

    service = LeaveLogService(db)

    leave_log = service.create_leave_log(
        caller=caller,
        payload=payload,
    )

    db.commit()

    return success_response(
        status_code=http_status.HTTP_201_CREATED,
        status_message="Leave log created successfully",
        response_data=leave_log,
    )


@router.get(
    "",
    response_model=APIResponse[list[LeaveLogRead]],
    status_code=http_status.HTTP_200_OK,
)
def list_leave_logs(
    id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    leave_type: LeaveType | None = None,
    leave_date: date | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> APIResponse[list[LeaveLogRead]]:

    service = LeaveLogService(db)

    leave_logs = service.list_leave_logs(
        id=id,
        user_id=user_id,
        leave_type=leave_type,
        leave_date=leave_date,
    )

    return success_response(
        status_code=http_status.HTTP_200_OK,
        status_message="Leave logs retrieved successfully",
        response_data=leave_logs,
    )


@router.patch(
    "/{leave_log_id}",
    response_model=APIResponse[LeaveLogRead],
    status_code=http_status.HTTP_200_OK,
)
def update_leave_log(
    leave_log_id: uuid.UUID,
    payload: LeaveLogUpdate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
    service: LeaveLogService = Depends(get_leave_log_service),
) -> APIResponse[LeaveLogRead]:

    service = LeaveLogService(db)

    leave_log = service.update_leave_log(
        leave_log_id=leave_log_id,
        payload=payload,
        caller=caller,
    )

    db.commit()

    return success_response(
        status_code=http_status.HTTP_200_OK,
        status_message="Leave log updated successfully",
        response_data=leave_log,
    )


@router.delete(
    "/{leave_log_id}",
    response_model=APIResponse[None],
    status_code=http_status.HTTP_200_OK,
)
def delete_leave_log(
    leave_log_id: uuid.UUID,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
    service: LeaveLogService = Depends(get_leave_log_service),
) -> APIResponse[None]:

    service = LeaveLogService(db)

    service.delete_leave_log(
        leave_log_id=leave_log_id,
        caller=caller,
    )

    db.commit()

    return success_response(
        status_code=http_status.HTTP_200_OK,
        status_message="Leave log deleted successfully",
        response_data=None,
    )
