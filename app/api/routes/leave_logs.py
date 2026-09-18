import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.enums import LeaveType, UserRole
from app.models.timesheet import LeaveLog
from app.models.user import User
from app.schemas.common_response import APIResponse, success_response, COMMON_RESPONSES
from app.schemas.leave_log import LeaveLogCreate, LeaveLogRead, LeaveLogUpdate

router = APIRouter(
    prefix="/leave-logs",
    tags=["leave-logs"],
    responses=COMMON_RESPONSES,
)


@router.post(
    "",
    response_model=APIResponse[LeaveLogRead],
    status_code=status.HTTP_201_CREATED,
)
def create_leave_log(
    payload: LeaveLogCreate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[LeaveLogRead]:
    leave_log = LeaveLog(
        organization_id=caller.organization_id,
        user_id=caller.id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        leave_type=payload.leave_type,
        reason=payload.reason,
    )

    db.add(leave_log)

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Overlapping leave already exists for this period",
        )

    db.refresh(leave_log)
    db.commit()

    return success_response(
        status_code=status.HTTP_201_CREATED,
        status_message="Leave log created successfully",
        response_data=leave_log,
    )


@router.get(
    "",
    response_model=APIResponse[list[LeaveLogRead]],
)
def list_leave_logs(
    id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    leave_type: LeaveType | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> APIResponse[list[LeaveLogRead]]:
    stmt = select(LeaveLog).where(LeaveLog.deleted_at.is_(None))

    if id is not None:
        stmt = stmt.where(LeaveLog.id == id)

    if user_id is not None:
        stmt = stmt.where(LeaveLog.user_id == user_id)

    if leave_type is not None:
        stmt = stmt.where(LeaveLog.leave_type == leave_type)

    leave_logs = list(db.scalars(stmt))

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Leave logs retrieved successfully",
        response_data=leave_logs,
    )


def _can_update(
    caller: User,
    leave_log: LeaveLog,
) -> bool:
    if caller.role in (
        UserRole.admin,
        UserRole.manager,
    ):
        return True

    return leave_log.user_id == caller.id and leave_log.start_date > date.today()


def _can_delete(
    caller: User,
    leave_log: LeaveLog,
) -> bool:
    return leave_log.user_id == caller.id and leave_log.start_date > date.today()


@router.patch(
    "/{leave_log_id}",
    response_model=APIResponse[LeaveLogRead],
)
def update_leave_log(
    leave_log_id: uuid.UUID,
    payload: LeaveLogUpdate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[LeaveLogRead]:
    leave_log = db.get(
        LeaveLog,
        leave_log_id,
    )

    if leave_log is None or leave_log.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Leave log not found",
        )

    if not _can_update(caller, leave_log):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(leave_log, field, value)

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Overlapping leave already exists for this period",
        )

    db.refresh(leave_log)
    db.commit()

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Leave log updated successfully",
        response_data=leave_log,
    )


@router.delete(
    "/{leave_log_id}",
    response_model=APIResponse[None],
    status_code=status.HTTP_200_OK,
)
def delete_leave_log(
    leave_log_id: uuid.UUID,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[None]:
    leave_log = db.get(
        LeaveLog,
        leave_log_id,
    )

    if leave_log is None or leave_log.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Leave log not found",
        )

    if not _can_delete(caller, leave_log):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    leave_log.deleted_at = datetime.now(timezone.utc)
    leave_log.deleted_by = caller.id

    db.commit()

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Leave log deleted successfully",
        response_data=None,
    )
