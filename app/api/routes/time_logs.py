import uuid
from datetime import date

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.pagination import Pagination, get_pagination
from app.core.database import get_db
from app.models.user import User
from app.schemas.common_response import APIResponse, success_response
from app.schemas.time_log import TimeLogCreate, TimeLogRead, TimeLogUpdate
from app.services.time_log import TimeLogService

router = APIRouter(
    prefix="/time-logs",
    tags=["time-logs"],
)


def get_time_log_service(db: Session = Depends(get_db)) -> TimeLogService:
    return TimeLogService(db)


@router.post(
    "",
    response_model=APIResponse[TimeLogRead],
    status_code=status.HTTP_201_CREATED,
)
def create_time_log(
    payload: TimeLogCreate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
    service: TimeLogService = Depends(get_time_log_service),
) -> APIResponse[TimeLogRead]:
    time_log = service.create_time_log(payload=payload, caller=caller)
    db.commit()

    return success_response(
        status_code=status.HTTP_201_CREATED,
        status_message="Time log created successfully",
        response_data=time_log,
    )


@router.get(
    "",
    response_model=APIResponse[list[TimeLogRead]],
)
def list_time_logs(
    id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None,
    activity_id: uuid.UUID | None = None,
    log_date: date | None = None,
    pagination: Pagination = Depends(get_pagination),
    caller: User = Depends(get_current_user),
    service: TimeLogService = Depends(get_time_log_service),
) -> APIResponse[list[TimeLogRead]]:
    time_logs = service.list_time_logs(
        caller=caller,
        pagination=pagination,
        log_id=id,
        user_id=user_id,
        task_id=task_id,
        activity_id=activity_id,
        log_date=log_date,
    )

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Time logs retrieved successfully",
        response_data=time_logs,
    )


@router.patch(
    "/{time_log_id}",
    response_model=APIResponse[TimeLogRead],
)
def update_time_log(
    time_log_id: uuid.UUID,
    payload: TimeLogUpdate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
    service: TimeLogService = Depends(get_time_log_service),
) -> APIResponse[TimeLogRead]:
    time_log = service.update_time_log(
        time_log_id=time_log_id, payload=payload, caller=caller
    )
    db.commit()

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Time log updated successfully",
        response_data=time_log,
    )


@router.delete(
    "/{time_log_id}",
    response_model=APIResponse[None],
    status_code=status.HTTP_200_OK,
)
def delete_time_log(
    time_log_id: uuid.UUID,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
    service: TimeLogService = Depends(get_time_log_service),
) -> APIResponse[None]:
    service.delete_time_log(time_log_id=time_log_id, caller=caller)
    db.commit()

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Time log deleted successfully",
        response_data=None,
    )
