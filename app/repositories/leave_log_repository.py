import uuid
from datetime import date

from sqlalchemy import select

from app.models.enums import LeaveType
from app.models.timesheet import LeaveLog, LeaveLogDay
from app.repositories.base_repository import BaseRepository


class LeaveLogRepository(BaseRepository[LeaveLog]):
    model = LeaveLog

    def get_active_by_id(
        self,
        leave_log_id: uuid.UUID,
    ) -> LeaveLog | None:

        stmt = select(LeaveLog).where(
            LeaveLog.id == leave_log_id,
            LeaveLog.deleted_at.is_(None),
        )

        return self.db.scalar(stmt)

    def list_filtered(
        self,
        *,
        id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        leave_type: LeaveType | None = None,
        leave_date: date | None = None,
    ) -> list[LeaveLog]:

        stmt = select(LeaveLog).where(LeaveLog.deleted_at.is_(None))

        if id is not None:
            stmt = stmt.where(LeaveLog.id == id)

        if user_id is not None:
            stmt = stmt.where(LeaveLog.user_id == user_id)

        if leave_type is not None:
            stmt = stmt.where(LeaveLog.leave_type == leave_type)

        if leave_date is not None:
            stmt = (
                stmt.join(
                    LeaveLogDay,
                    LeaveLogDay.leave_log_id == LeaveLog.id,
                )
                .where(
                    LeaveLogDay.leave_date == leave_date,
                    LeaveLogDay.deleted_at.is_(None),
                )
                .distinct()
            )

        stmt = stmt.order_by(
            LeaveLog.start_date,
            LeaveLog.created_at,
        )

        return list(self.db.scalars(stmt))
