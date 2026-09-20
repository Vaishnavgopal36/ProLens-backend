import uuid

from sqlalchemy import select

from app.models.task import TaskAssignee
from app.repositories.base_repository import BaseRepository


class TaskAssigneeRepository(BaseRepository[TaskAssignee]):
    model = TaskAssignee

    def is_active_assignee(self, task_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        return (
            self.db.scalar(
                select(TaskAssignee).where(
                    TaskAssignee.task_id == task_id,
                    TaskAssignee.user_id == user_id,
                    TaskAssignee.removed_at.is_(None),
                )
            )
            is not None
        )