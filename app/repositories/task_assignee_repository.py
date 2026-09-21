import uuid
from datetime import date

from sqlalchemy import select

from app.models.task import TaskAssignee
from app.models.timesheet import LeaveLog
from app.repositories.base_repository import BaseRepository


class TaskAssigneeRepository(BaseRepository[TaskAssignee]):
    model = TaskAssignee

    def get_active_by_id(self, assignee_id: uuid.UUID) -> TaskAssignee | None:
        assignee = self.get_by_id(assignee_id)

        if assignee is None or assignee.removed_at is not None:
            return None

        return assignee

    def get_active_by_task_and_user(
        self, task_id: uuid.UUID, user_id: uuid.UUID
    ) -> TaskAssignee | None:
        return self.db.scalar(
            select(TaskAssignee).where(
                TaskAssignee.task_id == task_id,
                TaskAssignee.user_id == user_id,
                TaskAssignee.removed_at.is_(None),
            )
        )

    def is_active_assignee(self, task_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        return self.get_active_by_task_and_user(task_id, user_id) is not None

    def list_filtered(
        self,
        *,
        id: uuid.UUID | None = None,
        task_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TaskAssignee]:
        stmt = select(TaskAssignee).where(TaskAssignee.removed_at.is_(None))

        if id is not None:
            stmt = stmt.where(TaskAssignee.id == id)
        if task_id is not None:
            stmt = stmt.where(TaskAssignee.task_id == task_id)
        if user_id is not None:
            stmt = stmt.where(TaskAssignee.user_id == user_id)

        stmt = stmt.order_by(TaskAssignee.assigned_at, TaskAssignee.id)
        return list(self.db.scalars(stmt.limit(limit).offset(offset)))

    def get_conflicting_leave(
        self,
        user_id: uuid.UUID,
        window_start: date | None,
        window_end: date | None,
    ) -> LeaveLog | None:
        """A live leave of the user overlapping [window_start, window_end] (inclusive).

        With only one bound known the window collapses to that single day; with
        neither there is nothing to conflict with.
        """
        window_start = window_start or window_end
        window_end = window_end or window_start
        if window_start is None or window_end is None:
            return None

        return self.db.scalar(
            select(LeaveLog)
            .where(
                LeaveLog.user_id == user_id,
                LeaveLog.deleted_at.is_(None),
                LeaveLog.start_date <= window_end,
                LeaveLog.end_date >= window_start,
            )
            .limit(1)
        )
