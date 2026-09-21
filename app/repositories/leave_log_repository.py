import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select

from app.models.enums import LeaveType
from app.models.timesheet import LeaveLog
from app.repositories.base_repository import BaseRepository


class LeaveLogRepository(BaseRepository[LeaveLog]):
    model = LeaveLog

    def get_active_by_id(self, leave_log_id: uuid.UUID) -> LeaveLog | None:
        leave_log = self.get_by_id(leave_log_id)
        if leave_log is None or leave_log.deleted_at is not None:
            return None
        return leave_log

    def list_filtered(
        self,
        *,
        limit: int,
        offset: int,
        id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        leave_type: LeaveType | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[LeaveLog]:
        stmt = select(LeaveLog).where(LeaveLog.deleted_at.is_(None))

        if id is not None:
            stmt = stmt.where(LeaveLog.id == id)
        if user_id is not None:
            stmt = stmt.where(LeaveLog.user_id == user_id)
        if leave_type is not None:
            stmt = stmt.where(LeaveLog.leave_type == leave_type)
        # Date-range overlap: leave intersects [from_date, to_date].
        if to_date is not None:
            stmt = stmt.where(LeaveLog.start_date <= to_date)
        if from_date is not None:
            stmt = stmt.where(LeaveLog.end_date >= from_date)

        stmt = stmt.order_by(LeaveLog.created_at, LeaveLog.id)
        return list(self.db.scalars(stmt.limit(limit).offset(offset)))

    def soft_delete(self, leave_log: LeaveLog, deleted_by: uuid.UUID) -> None:
        leave_log.deleted_at = datetime.now(timezone.utc)
        leave_log.deleted_by = deleted_by
        self.db.flush()
