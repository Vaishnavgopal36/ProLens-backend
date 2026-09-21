import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.models.enums import CalendarEventType
from app.models.timesheet import CalendarEvent
from app.repositories.base_repository import BaseRepository


class CalendarEventRepository(BaseRepository[CalendarEvent]):
    model = CalendarEvent

    def get_active_by_id(self, event_id: uuid.UUID) -> CalendarEvent | None:
        event = self.get_by_id(event_id)
        if event is None or event.deleted_at is not None:
            return None
        return event

    def get_active_by_source_leave_log(
        self, leave_log_id: uuid.UUID
    ) -> CalendarEvent | None:
        return self.db.scalar(
            select(CalendarEvent).where(
                CalendarEvent.source_leave_log_id == leave_log_id,
                CalendarEvent.deleted_at.is_(None),
            )
        )

    def list_filtered(
        self,
        *,
        limit: int,
        offset: int,
        id: uuid.UUID | None = None,
        event_type: CalendarEventType | None = None,
        range_start: datetime | None = None,
        range_end: datetime | None = None,
    ) -> list[CalendarEvent]:
        stmt = select(CalendarEvent).where(CalendarEvent.deleted_at.is_(None))

        if id is not None:
            stmt = stmt.where(CalendarEvent.id == id)
        if event_type is not None:
            stmt = stmt.where(CalendarEvent.event_type == event_type)
        # Overlap semantics: events crossing a range boundary are included.
        if range_end is not None:
            stmt = stmt.where(CalendarEvent.start_time <= range_end)
        if range_start is not None:
            stmt = stmt.where(CalendarEvent.end_time >= range_start)

        stmt = stmt.order_by(CalendarEvent.start_time, CalendarEvent.id)
        return list(self.db.scalars(stmt.limit(limit).offset(offset)))

    def soft_delete(self, event: CalendarEvent, deleted_by: uuid.UUID) -> None:
        event.deleted_at = datetime.now(timezone.utc)
        event.deleted_by = deleted_by
        self.db.flush()
