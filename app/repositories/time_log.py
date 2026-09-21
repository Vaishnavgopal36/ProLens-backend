import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select

from app.models.task import Activity, ActivityAssignee, Task, TaskAssignee
from app.models.timesheet import TimeLog
from app.repositories.base_repository import BaseRepository


class TimeLogRepository(BaseRepository[TimeLog]):
    model = TimeLog

    def get_active_by_id(self, time_log_id: uuid.UUID) -> TimeLog | None:
        time_log = self.get_by_id(time_log_id)
        if time_log is None or time_log.deleted_at is not None:
            return None
        return time_log

    def get_task(self, task_id: uuid.UUID) -> Task | None:
        return self.db.get(Task, task_id)

    def get_activity(self, activity_id: uuid.UUID) -> Activity | None:
        return self.db.get(Activity, activity_id)

    def is_task_assignee(self, task_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        return (
            self.db.scalar(
                select(TaskAssignee.id).where(
                    TaskAssignee.task_id == task_id,
                    TaskAssignee.user_id == user_id,
                    TaskAssignee.removed_at.is_(None),
                )
            )
            is not None
        )

    def is_activity_assignee(self, activity_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        return (
            self.db.scalar(
                select(ActivityAssignee.id).where(
                    ActivityAssignee.activity_id == activity_id,
                    ActivityAssignee.user_id == user_id,
                    ActivityAssignee.removed_at.is_(None),
                )
            )
            is not None
        )

    def list_filtered(
        self,
        *,
        limit: int,
        offset: int,
        id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        task_id: uuid.UUID | None = None,
        activity_id: uuid.UUID | None = None,
        log_date: date | None = None,
    ) -> list[TimeLog]:
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

        stmt = stmt.order_by(TimeLog.created_at, TimeLog.id)
        return list(self.db.scalars(stmt.limit(limit).offset(offset)))

    def soft_delete(self, time_log: TimeLog, deleted_by: uuid.UUID) -> None:
        time_log.deleted_at = datetime.now(timezone.utc)
        time_log.deleted_by = deleted_by
        self.db.flush()
