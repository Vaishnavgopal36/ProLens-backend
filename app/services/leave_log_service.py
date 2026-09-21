import uuid
from datetime import date, datetime, time, timezone

from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from app.api.pagination import Pagination
from app.core.exception import AppException, InsufficientPermissionError
from app.models.enums import CalendarEventType, LeaveType, UserRole
from app.models.timesheet import CalendarEvent, LeaveLog
from app.models.user import User
from app.repositories.calendar_event_repository import CalendarEventRepository
from app.repositories.leave_log_repository import LeaveLogRepository
from app.repositories.user_repository import UserRepository
from app.schemas.leave_log import LeaveLogCreate, LeaveLogRead, LeaveLogUpdate

MANAGER_ROLES = (UserRole.admin, UserRole.super_admin, UserRole.manager)

_OVERLAP_CONSTRAINT = "excl_leave_logs_no_overlap"
_EXCLUSION_VIOLATION = "23P01"


class LeaveLogNotFoundError(AppException):
    status_code = 404
    status_message = "Not Found"
    default_message = "Leave log not found"


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _event_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(start, time.min, tzinfo=timezone.utc),
        datetime.combine(end, time(23, 59, 59), tzinfo=timezone.utc),
    )


def _is_overlap_violation(exc: IntegrityError) -> bool:
    orig = exc.orig
    constraint = getattr(getattr(orig, "diag", None), "constraint_name", None)
    return (
        getattr(orig, "pgcode", None) == _EXCLUSION_VIOLATION
        or constraint == _OVERLAP_CONSTRAINT
    )


class LeaveLogService:

    def __init__(self, db: Session):
        self.db = db
        self.leave_logs = LeaveLogRepository(db)
        self.events = CalendarEventRepository(db)
        self.users = UserRepository(db)

    # -- helpers -----------------------------------------------------------

    def _flush(self) -> None:
        try:
            self.db.flush()
        except IntegrityError as exc:
            if _is_overlap_violation(exc):
                raise AppException(
                    "Overlapping leave already exists",
                    status_code=409,
                    status_message="Conflict",
                ) from exc
            raise AppException(
                "Leave log violates a data integrity rule",
                status_code=400,
                status_message="Bad Request",
            ) from exc
        except DataError as exc:
            raise AppException(
                "Invalid leave log data",
                status_code=422,
                status_message="Unprocessable Entity",
            ) from exc

    def serialize(self, leave_log: LeaveLog, caller: User) -> LeaveLogRead:
        """`reason` is private to the owner, managers and admins."""
        data = LeaveLogRead.model_validate(leave_log)
        if leave_log.user_id != caller.id and caller.role not in MANAGER_ROLES:
            data.reason = None
        return data

    def _get_leave_log(self, leave_log_id: uuid.UUID, caller: User) -> LeaveLog:
        leave_log = self.leave_logs.get_active_by_id(leave_log_id)
        if leave_log is None or (
            caller.role != UserRole.super_admin
            and leave_log.organization_id != caller.organization_id
        ):
            raise LeaveLogNotFoundError()
        return leave_log

    def _owner_title(self, user_id: uuid.UUID) -> str:
        owner = self.users.get_by_id(user_id)
        if owner is None:
            return "Employee on leave"
        name = " ".join(p for p in (owner.first_name, owner.last_name) if p)
        return f"{name or owner.email} on leave"

    # -- use cases ---------------------------------------------------------

    def create_leave_log(self, payload: LeaveLogCreate, caller: User) -> LeaveLogRead:
        leave_log = LeaveLog(
            organization_id=caller.organization_id,
            user_id=caller.id,
            start_date=payload.start_date,
            end_date=payload.end_date,
            leave_type=payload.leave_type,
            reason=payload.reason,
        )
        self.db.add(leave_log)
        self._flush()

        start, end = _event_bounds(payload.start_date, payload.end_date)
        self.events.add(
            CalendarEvent(
                organization_id=caller.organization_id,
                source_leave_log_id=leave_log.id,
                title=self._owner_title(caller.id),
                event_type=CalendarEventType.leave,
                start_time=start,
                end_time=end,
                created_by=caller.id,
            )
        )
        self.db.refresh(leave_log)
        return self.serialize(leave_log, caller)

    def list_leave_logs(
        self,
        caller: User,
        pagination: Pagination,
        leave_log_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        leave_type: LeaveType | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[LeaveLogRead]:
        leave_logs = self.leave_logs.list_filtered(
            limit=pagination.limit,
            offset=pagination.offset,
            id=leave_log_id,
            user_id=user_id,
            leave_type=leave_type,
            from_date=from_date,
            to_date=to_date,
        )
        return [self.serialize(leave_log, caller) for leave_log in leave_logs]

    def update_leave_log(
        self, leave_log_id: uuid.UUID, payload: LeaveLogUpdate, caller: User
    ) -> LeaveLogRead:
        leave_log = self._get_leave_log(leave_log_id, caller)
        update_data = payload.model_dump(exclude_unset=True)

        is_employee = caller.role not in MANAGER_ROLES
        today = _utc_today()
        if is_employee and (
            leave_log.user_id != caller.id or leave_log.start_date <= today
        ):
            raise InsufficientPermissionError()

        new_start = update_data.get("start_date", leave_log.start_date)
        new_end = update_data.get("end_date", leave_log.end_date)
        if new_start > new_end:
            raise AppException(
                "start_date must be on or before end_date",
                status_code=422,
                status_message="Unprocessable Entity",
            )
        if is_employee and new_start < today:
            raise AppException(
                "Leave cannot be moved into the past",
                status_code=422,
                status_message="Unprocessable Entity",
            )

        for field, value in update_data.items():
            setattr(leave_log, field, value)
        self._flush()

        event = self.events.get_active_by_source_leave_log(leave_log.id)
        if event is not None:
            event.start_time, event.end_time = _event_bounds(new_start, new_end)
            self._flush()

        self.db.refresh(leave_log)
        return self.serialize(leave_log, caller)

    def delete_leave_log(self, leave_log_id: uuid.UUID, caller: User) -> None:
        leave_log = self._get_leave_log(leave_log_id, caller)

        if leave_log.user_id != caller.id or leave_log.start_date <= _utc_today():
            raise InsufficientPermissionError()

        self.leave_logs.soft_delete(leave_log, deleted_by=caller.id)

        event = self.events.get_active_by_source_leave_log(leave_log.id)
        if event is not None:
            self.events.soft_delete(event, deleted_by=caller.id)
