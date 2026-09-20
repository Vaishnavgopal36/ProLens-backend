# app/services/task_service.py

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exception import (
    FeatureNotFoundError,
    InsufficientPermissionError,
    NotProjectMemberError,
    TaskNotFoundError,
)
from app.models.enums import EntityStatus, PriorityLevel, UserRole
from app.models.task import Task
from app.models.user import User
from app.repositories.feature_repository import FeatureRepository
from app.repositories.project_member_repository import ProjectMemberRepository
from app.repositories.task_assignee_repository import TaskAssigneeRepository
from app.repositories.task_repository import TaskRepository
from app.schemas.task import TaskCreate, TaskUpdate


class TaskService:
    def __init__(self, db: Session):
        self.db = db
        self.tasks = TaskRepository(db)
        self.features = FeatureRepository(db)
        self.project_members = ProjectMemberRepository(db)
        self.task_assignees = TaskAssigneeRepository(db)

    def _project_id_for_task(self, task: Task) -> uuid.UUID | None:
        if task.feature_id is None:
            return None

        feature = self.features.get_by_id(task.feature_id)
        return feature.project_id if feature else None

    def _can_write(self, caller: User, task: Task, *, for_delete: bool = False) -> bool:
        if caller.role == UserRole.admin:
            return True

        if caller.role == UserRole.manager:
            project_id = self._project_id_for_task(task)
            if project_id is None:
                return True
            return self.project_members.is_member(project_id, caller.id)

        if caller.role == UserRole.employee:
            if self.task_assignees.is_active_assignee(task.id, caller.id):
                return True
            if for_delete and task.created_by == caller.id:
                return True
            return False

        return False

    def create_task(self, caller: User, payload: TaskCreate) -> Task:
        if payload.feature_id is not None:
            feature = self.features.get_active_by_id(payload.feature_id)
            if feature is None:
                raise FeatureNotFoundError()

            if caller.role == UserRole.manager and not self.project_members.is_member(
                feature.project_id, caller.id
            ):
                raise NotProjectMemberError()

        task = Task(
            organization_id=caller.organization_id,
            feature_id=payload.feature_id,
            name=payload.name,
            description=payload.description,
            priority=payload.priority or PriorityLevel.medium,
            start_date=payload.start_date,
            due_date=payload.due_date,
            created_by=caller.id,
        )

        return self.tasks.add(task)

    def list_tasks(
        self,
        *,
        id: uuid.UUID | None = None,
        feature_id: uuid.UUID | None = None,
        status: EntityStatus | None = None,
        priority: PriorityLevel | None = None,
    ) -> list[Task]:
        return self.tasks.list_filtered(id=id, feature_id=feature_id, status=status, priority=priority)

    def update_task(self, caller: User, task_id: uuid.UUID, payload: TaskUpdate) -> Task:
        task = self.tasks.get_active_by_id(task_id)
        if task is None:
            raise TaskNotFoundError()

        if not self._can_write(caller, task):
            raise InsufficientPermissionError()

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(task, field, value)
        task.updated_by = caller.id

        self.db.flush()
        self.db.refresh(task)
        return task

    def delete_task(self, caller: User, task_id: uuid.UUID) -> None:
        task = self.tasks.get_active_by_id(task_id)
        if task is None:
            raise TaskNotFoundError()

        if not self._can_write(caller, task, for_delete=True):
            raise InsufficientPermissionError()

        task.deleted_at = datetime.now(timezone.utc)
        task.deleted_by = caller.id
        self.db.flush()