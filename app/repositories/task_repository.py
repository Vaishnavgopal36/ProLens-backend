import uuid

from sqlalchemy import select

from app.models.enums import EntityStatus, PriorityLevel
from app.models.task import Task
from app.repositories.base_repository import BaseRepository


class TaskRepository(BaseRepository[Task]):
    model = Task

    def get_active_by_id(self, task_id: uuid.UUID) -> Task | None:
        task = self.db.get(Task, task_id)
        if task is None or task.deleted_at is not None:
            return None
        return task

    def list_filtered(
        self,
        *,
        id: uuid.UUID | None = None,
        feature_id: uuid.UUID | None = None,
        status: EntityStatus | None = None,
        priority: PriorityLevel | None = None,
    ) -> list[Task]:
        stmt = select(Task).where(Task.deleted_at.is_(None))

        if id is not None:
            stmt = stmt.where(Task.id == id)
        if feature_id is not None:
            stmt = stmt.where(Task.feature_id == feature_id)
        if status is not None:
            stmt = stmt.where(Task.status == status)
        if priority is not None:
            stmt = stmt.where(Task.priority == priority)

        return list(self.db.scalars(stmt))