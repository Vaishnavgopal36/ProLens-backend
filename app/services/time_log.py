import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.api.pagination import Pagination
from app.core.exception import (
    AppException,
    InsufficientPermissionError,
    TaskNotFoundError,
)
from app.models.enums import UserRole
from app.models.timesheet import TimeLog
from app.models.user import User
from app.repositories.time_log import TimeLogRepository
from app.schemas.time_log import TimeLogCreate, TimeLogUpdate
from app.services.activity import ActivityNotFoundError

ADMIN_ROLES = (UserRole.admin, UserRole.super_admin)


class TimeLogNotFoundError(AppException):
    status_code = 404
    status_message = "Not Found"
    default_message = "Time log not found"


class TimeLogService:
    def __init__(self, db: Session):
        self.db = db
        self.time_logs = TimeLogRepository(db)

    def _require_assigned_target(self, payload: TimeLogCreate, caller: User) -> None:
        is_admin = caller.role in ADMIN_ROLES

        if payload.task_id is not None:
            task = self.time_logs.get_task(payload.task_id)
            if (
                task is None
                or task.deleted_at is not None
                or task.organization_id != caller.organization_id
            ):
                raise TaskNotFoundError()
            if not is_admin and not self.time_logs.is_task_assignee(task.id, caller.id):
                raise InsufficientPermissionError("You are not assigned to this task")
            return

        activity = self.time_logs.get_activity(payload.activity_id)
        if (
            activity is None
            or activity.deleted_at is not None
            or activity.organization_id != caller.organization_id
        ):
            raise ActivityNotFoundError()
        if not is_admin and not self.time_logs.is_activity_assignee(
            activity.id, caller.id
        ):
            raise InsufficientPermissionError("You are not assigned to this activity")

    def create_time_log(self, payload: TimeLogCreate, caller: User) -> TimeLog:
        self._require_assigned_target(payload, caller)

        time_log = TimeLog(
            organization_id=caller.organization_id,
            user_id=caller.id,
            task_id=payload.task_id,
            activity_id=payload.activity_id,
            log_date=payload.log_date,
            duration_minutes=payload.duration_minutes,
            description=payload.description,
        )
        return self.time_logs.add(time_log)

    def list_time_logs(
        self,
        caller: User,
        pagination: Pagination,
        log_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        task_id: uuid.UUID | None = None,
        activity_id: uuid.UUID | None = None,
        log_date: date | None = None,
    ) -> list[TimeLog]:
        if caller.role == UserRole.employee:
            if user_id is not None and user_id != caller.id:
                raise InsufficientPermissionError(
                    "Employees can only view their own time logs"
                )
            user_id = caller.id

        return self.time_logs.list_filtered(
            limit=pagination.limit,
            offset=pagination.offset,
            id=log_id,
            user_id=user_id,
            task_id=task_id,
            activity_id=activity_id,
            log_date=log_date,
        )

    def _get_own_time_log(self, time_log_id: uuid.UUID, caller: User) -> TimeLog:
        time_log = self.time_logs.get_active_by_id(time_log_id)
        if time_log is None or time_log.organization_id != caller.organization_id:
            raise TimeLogNotFoundError()
        if time_log.user_id != caller.id:
            raise InsufficientPermissionError()
        return time_log

    def update_time_log(
        self, time_log_id: uuid.UUID, payload: TimeLogUpdate, caller: User
    ) -> TimeLog:
        time_log = self._get_own_time_log(time_log_id, caller)

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(time_log, field, value)

        self.db.flush()
        self.db.refresh(time_log)
        return time_log

    def delete_time_log(self, time_log_id: uuid.UUID, caller: User) -> None:
        time_log = self._get_own_time_log(time_log_id, caller)
        self.time_logs.soft_delete(time_log, deleted_by=caller.id)
