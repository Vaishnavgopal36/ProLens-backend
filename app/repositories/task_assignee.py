import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.project import Feature, ProjectMember
from app.models.task import Task, TaskAssignee
from app.models.user import User


class TaskAssigneeRepository:

    def __init__(self, db: Session):
        self.db = db

    def get_task_by_id(self, task_id: uuid.UUID) -> Task | None:
        return self.db.get(Task, task_id)

    def get_active_assignee(
        self, task_id: uuid.UUID, user_id: uuid.UUID
    ) -> TaskAssignee | None:
        return self.db.scalar(
            select(TaskAssignee).where(
                TaskAssignee.task_id == task_id,
                TaskAssignee.user_id == user_id,
                TaskAssignee.removed_at.is_(None),
            )
        )

    def get_active_assignee_by_id(
        self, assignee_id: uuid.UUID
    ) -> TaskAssignee | None:
        assignee = self.db.get(TaskAssignee, assignee_id)
        if assignee is None or assignee.removed_at is not None:
            return None
        return assignee

    def is_project_member(
        self, project_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        return (
            self.db.scalar(
                select(ProjectMember).where(
                    ProjectMember.project_id == project_id,
                    ProjectMember.user_id == user_id,
                    ProjectMember.removed_at.is_(None),
                )
            )
            is not None
        )

    def get_feature_by_id(self, feature_id: uuid.UUID) -> Feature | None:
        return self.db.get(Feature, feature_id)

    def create(
        self,
        organization_id: uuid.UUID,
        task_id: uuid.UUID,
        user_id: uuid.UUID,
        assigned_by: uuid.UUID,
    ) -> TaskAssignee:
        assignee = TaskAssignee(
            organization_id=organization_id,
            task_id=task_id,
            user_id=user_id,
            assigned_by=assigned_by,
        )
        self.db.add(assignee)
        self.db.flush()
        self.db.refresh(assignee)
        self.db.commit()
        return assignee

    def list(
        self,
        assignee_id: uuid.UUID | None = None,
        task_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> list[TaskAssignee]:
        stmt = select(TaskAssignee).where(TaskAssignee.removed_at.is_(None))

        if assignee_id is not None:
            stmt = stmt.where(TaskAssignee.id == assignee_id)
        if task_id is not None:
            stmt = stmt.where(TaskAssignee.task_id == task_id)
        if user_id is not None:
            stmt = stmt.where(TaskAssignee.user_id == user_id)

        return list(self.db.scalars(stmt))

    def soft_delete(self, assignee: TaskAssignee, removed_by: uuid.UUID) -> None:
        assignee.removed_at = datetime.now(timezone.utc)
        assignee.removed_by = removed_by
        self.db.commit()