import uuid
from datetime import date

from sqlalchemy import select

from app.models.timesheet import LeaveLogDay
from app.repositories.base_repository import BaseRepository


class LeaveLogDayRepository(BaseRepository[LeaveLogDay]):
    model = LeaveLogDay

    def list_active_by_leave_log(
        self,
        leave_log_id: uuid.UUID,
    ) -> list[LeaveLogDay]:

        stmt = (
            select(LeaveLogDay)
            .where(
                LeaveLogDay.leave_log_id == leave_log_id,
                LeaveLogDay.deleted_at.is_(None),
            )
            .order_by(LeaveLogDay.leave_date)
        )

        return list(self.db.scalars(stmt))

    def get_by_leave_log_and_date(
        self,
        *,
        leave_log_id: uuid.UUID,
        leave_date: date,
    ) -> LeaveLogDay | None:

        stmt = select(LeaveLogDay).where(
            LeaveLogDay.leave_log_id == leave_log_id,
            LeaveLogDay.leave_date == leave_date,
        )

        return self.db.scalar(stmt)

    def has_overlapping_leave(
        self,
        *,
        user_id: uuid.UUID,
        leave_date: date,
        slot,
        exclude_leave_log_id: uuid.UUID | None = None,
    ) -> bool:

        stmt = select(LeaveLogDay.id).where(
            LeaveLogDay.user_id == user_id,
            LeaveLogDay.leave_date == leave_date,
            LeaveLogDay.deleted_at.is_(None),
            LeaveLogDay.slot.op("&&")(slot),
        )

        if exclude_leave_log_id is not None:
            stmt = stmt.where(LeaveLogDay.leave_log_id != exclude_leave_log_id)

        return self.db.scalar(stmt.limit(1)) is not None
