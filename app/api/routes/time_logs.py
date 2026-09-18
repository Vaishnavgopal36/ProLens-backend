import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.timesheet import TimeLog
from app.models.user import User
from app.schemas.common_response import APIResponse, success_response, COMMON_RESPONSES
from app.schemas.time_log import TimeLogCreate, TimeLogRead, TimeLogUpdate

router = APIRouter(
    prefix="/time-logs",
    tags=["time-logs"],
    responses=COMMON_RESPONSES,
)


@router.post(
    "",
    response_model=APIResponse[TimeLogRead],
    status_code=status.HTTP_201_CREATED,
)
def create_time_log(
    payload: TimeLogCreate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[TimeLogRead]:
    time_log = TimeLog(
        organization_id=caller.organization_id,
        user_id=caller.id,
        task_id=payload.task_id,
        activity_id=payload.activity_id,
        log_date=payload.log_date,
        duration_minutes=payload.duration_minutes,
        description=payload.description,
    )

    db.add(time_log)
    db.flush()
    db.refresh(time_log)
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
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> APIResponse[list[TimeLogRead]]:
    stmt = select(TimeLog).where(TimeLog.deleted_at.is_(None))

    if id is not None:
        stmt = stmt.where(TimeLog.id == id)

    if user_id is not None:
        stmt = stmt.where(TimeLog.user_id == user_id)

    if task_id is not None:
        stmt = stmt.where(TimeLog.task_id == task_id)

    if activity_id is not None:
        stmt = stmt.where(TimeLog.activity_id == activity_id)

    if log_date is not None:
        stmt = stmt.where(TimeLog.log_date == log_date)

    time_logs = list(db.scalars(stmt))

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
) -> APIResponse[TimeLogRead]:
    time_log = db.get(
        TimeLog,
        time_log_id,
    )

    if time_log is None or time_log.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Time log not found",
        )

    if time_log.user_id != caller.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(time_log, field, value)

    db.flush()
    db.refresh(time_log)
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
) -> APIResponse[None]:
    time_log = db.get(
        TimeLog,
        time_log_id,
    )

    if time_log is None or time_log.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Time log not found",
        )

    if time_log.user_id != caller.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    time_log.deleted_at = datetime.now(timezone.utc)
    time_log.deleted_by = caller.id

    db.commit()

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Time log deleted successfully",
        response_data=None,
    )
