import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.api.pagination import Pagination
from app.core.exception import AppException, InsufficientPermissionError
from app.models.enums import CalendarEventType, UserRole
from app.models.timesheet import CalendarEvent
from app.models.user import User
from app.repositories.calendar_event_repository import CalendarEventRepository
from app.schemas.calendar_event import CalendarEventCreate, CalendarEventUpdate

ADMIN_ROLES = (UserRole.admin, UserRole.super_admin)
MANAGER_ROLES = (*ADMIN_ROLES, UserRole.manager)

# Minimum role per event type. `leave` is absent: it is system-generated only.
_CREATE_ROLES: dict[CalendarEventType, tuple[UserRole, ...]] = {
    CalendarEventType.holiday: ADMIN_ROLES,
    CalendarEventType.milestone: MANAGER_ROLES,
    CalendarEventType.release: MANAGER_ROLES,
    CalendarEventType.team_event: (*MANAGER_ROLES, UserRole.employee),
}


class CalendarEventNotFoundError(AppException):
    status_code = 404
    status_message = "Not Found"
    default_message = "Calendar event not found"


class CalendarEventService:
    def __init__(self, db: Session):
        self.db = db
        self.events = CalendarEventRepository(db)

    @staticmethod
    def _require_type_permission(event_type: CalendarEventType, caller: User) -> None:
        if event_type == CalendarEventType.leave:
            raise InsufficientPermissionError(
                "Leave events are managed automatically from leave logs"
            )
        if caller.role not in _CREATE_ROLES[event_type]:
            raise InsufficientPermissionError(
                f"You are not allowed to manage {event_type.value} events"
            )

    def create_event(self, payload: CalendarEventCreate, caller: User) -> CalendarEvent:
        self._require_type_permission(payload.event_type, caller)

        event = CalendarEvent(
            organization_id=caller.organization_id,
            title=payload.title,
            description=payload.description,
            event_type=payload.event_type,
            start_time=payload.start_time,
            end_time=payload.end_time,
            created_by=caller.id,
        )
        return self.events.add(event)

    def list_events(
        self,
        pagination: Pagination,
        event_id: uuid.UUID | None = None,
        event_type: CalendarEventType | None = None,
        range_start: datetime | None = None,
        range_end: datetime | None = None,
    ) -> list[CalendarEvent]:
        return self.events.list_filtered(
            limit=pagination.limit,
            offset=pagination.offset,
            id=event_id,
            event_type=event_type,
            range_start=range_start,
            range_end=range_end,
        )

    def _get_modifiable(self, event_id: uuid.UUID, caller: User) -> CalendarEvent:
        event = self.events.get_active_by_id(event_id)
        if event is None or (
            caller.role != UserRole.super_admin
            and event.organization_id != caller.organization_id
        ):
            raise CalendarEventNotFoundError()

        if event.event_type == CalendarEventType.leave or (
            event.source_leave_log_id is not None
        ):
            raise InsufficientPermissionError(
                "Leave events are managed automatically from leave logs"
            )
        if caller.role not in ADMIN_ROLES and event.created_by != caller.id:
            raise InsufficientPermissionError()
        return event

    def update_event(
        self, event_id: uuid.UUID, payload: CalendarEventUpdate, caller: User
    ) -> CalendarEvent:
        event = self._get_modifiable(event_id, caller)
        update_data = payload.model_dump(exclude_unset=True)

        if "event_type" in update_data:
            self._require_type_permission(update_data["event_type"], caller)

        new_start = update_data.get("start_time", event.start_time)
        new_end = update_data.get("end_time", event.end_time)
        if new_end < new_start:
            raise AppException(
                "end_time must be on or after start_time",
                status_code=422,
                status_message="Unprocessable Entity",
            )

        for field, value in update_data.items():
            setattr(event, field, value)

        self.db.flush()
        self.db.refresh(event)
        return event

    def delete_event(self, event_id: uuid.UUID, caller: User) -> None:
        event = self._get_modifiable(event_id, caller)
        self.events.soft_delete(event, deleted_by=caller.id)
