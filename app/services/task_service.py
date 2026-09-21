import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exception import (
    AppException,
    FeatureNotFoundError,
    InsufficientPermissionError,
    MustBelongToOrganizationError,
    NotProjectMemberError,
    ProjectNotFoundError,
    TaskNotFoundError,
)
from app.models.enums import EntityStatus, PriorityLevel, UserRole
from app.models.project import Feature
from app.models.task import Task
from app.models.user import User
from app.repositories.feature_repository import FeatureRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.task_assignee_repository import TaskAssigneeRepository
from app.repositories.task_repository import TaskRepository
from app.schemas.task import TaskCreate, TaskUpdate

ADMIN_ROLES = (UserRole.admin, UserRole.super_admin)


class TaskService:
    """Task use cases.

    Access rules:
    - admin: everything in the organization.
    - manager: tasks/features of projects they are an active member of;
      standalone tasks (no feature) only when they created them.
    - employee: may create a personal task (no feature) or a task in a project
      they belong to; may update/delete only tasks they are an active assignee
      of (delete also when they created it); may never change ``feature_id``.

    Visibility (list): admins see the whole organization; everyone else sees
    tasks of their projects, tasks assigned to them and their own standalone tasks.
    """

    def __init__(self, db: Session):
        self.db = db
        self.tasks = TaskRepository(db)
        self.features = FeatureRepository(db)
        self.projects = ProjectRepository(db)
        self.task_assignees = TaskAssigneeRepository(db)

    def _feature_project_id(self, feature_id: uuid.UUID) -> uuid.UUID | None:
        feature = self.features.get_by_id(feature_id)
        return feature.project_id if feature else None

    def can_manage(self, caller: User, task: Task) -> bool:
        """Admin/manager access to a task (used for edits and assignee management)."""
        if caller.role in ADMIN_ROLES:
            return True

        if caller.role == UserRole.manager:
            if task.feature_id is None:
                return task.created_by == caller.id
            project_id = self._feature_project_id(task.feature_id)
            return project_id is not None and self.projects.is_member(
                project_id, caller.id
            )

        return False

    def _can_write(self, caller: User, task: Task, *, for_delete: bool = False) -> bool:
        if caller.role in (*ADMIN_ROLES, UserRole.manager):
            return self.can_manage(caller, task)

        if caller.role == UserRole.employee:
            if self.task_assignees.is_active_assignee(task.id, caller.id):
                return True
            return for_delete and task.created_by == caller.id

        return False

    def _get_usable_feature(
        self, feature_id: uuid.UUID, organization_id: uuid.UUID
    ) -> Feature:
        """Feature that exists, is not soft-deleted, is in the org and has a live project."""
        feature = self.features.get_active_by_id(feature_id)
        if feature is None or feature.organization_id != organization_id:
            raise FeatureNotFoundError()

        if self.projects.get_active_by_id(feature.project_id) is None:
            raise ProjectNotFoundError()

        return feature

    def create_task(self, caller: User, payload: TaskCreate) -> Task:
        if caller.organization_id is None:
            raise MustBelongToOrganizationError()

        project_id = payload.project_id
        if payload.feature_id is not None:
            feature = self._get_usable_feature(
                payload.feature_id, caller.organization_id
            )
            project_id = feature.project_id

            if caller.role not in ADMIN_ROLES and not self.projects.is_member(
                feature.project_id, caller.id
            ):
                raise NotProjectMemberError()
        elif project_id is not None:
            proj = self.projects.get_active_by_id(project_id)
            if proj is None or proj.organization_id != caller.organization_id:
                raise ProjectNotFoundError()
            if caller.role not in ADMIN_ROLES and not self.projects.is_member(
                project_id, caller.id
            ):
                raise NotProjectMemberError()

        task = Task(
            organization_id=caller.organization_id,
            feature_id=payload.feature_id,
            project_id=project_id,
            name=payload.name,
            description=payload.description,
            priority=payload.priority or PriorityLevel.medium,
            estimated_hours=payload.estimated_hours,
            labels=payload.labels or [],
            subtasks=payload.subtasks or [],
            start_date=payload.start_date,
            due_date=payload.due_date,
            created_by=caller.id,
        )

        return self.tasks.add(task)

    def list_tasks(
        self,
        *,
        caller: User,
        id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        feature_id: uuid.UUID | None = None,
        status: EntityStatus | None = None,
        priority: PriorityLevel | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Task]:
        return self.tasks.list_filtered(
            caller=caller,
            id=id,
            project_id=project_id,
            feature_id=feature_id,
            status=status,
            priority=priority,
            limit=limit,
            offset=offset,
        )

    def _authorize_move(
        self, caller: User, task: Task, new_feature_id: uuid.UUID | None
    ) -> None:
        """Moving between features needs write access to the source and target project."""
        if caller.role not in (*ADMIN_ROLES, UserRole.manager):
            raise InsufficientPermissionError()

        # Source access was already verified by _can_write.
        if new_feature_id is None:
            return

        feature = self._get_usable_feature(new_feature_id, task.organization_id)

        if caller.role not in ADMIN_ROLES and not self.projects.is_member(
            feature.project_id, caller.id
        ):
            raise NotProjectMemberError()

    def update_task(
        self, caller: User, task_id: uuid.UUID, payload: TaskUpdate
    ) -> Task:
        task = self.tasks.get_active_by_id(task_id)
        if task is None:
            raise TaskNotFoundError()

        if not self._can_write(caller, task):
            raise InsufficientPermissionError()

        update_data = payload.model_dump(exclude_unset=True)

        if "feature_id" in update_data and update_data["feature_id"] != task.feature_id:
            self._authorize_move(caller, task, update_data["feature_id"])
        elif "feature_id" in update_data and caller.role == UserRole.employee:
            del update_data["feature_id"]  # unchanged value: not a move

        start = update_data.get("start_date", task.start_date)
        due = update_data.get("due_date", task.due_date)
        if start is not None and due is not None and start > due:
            raise AppException(
                "start_date must be on or before due_date",
                status_code=422,
                status_message="Unprocessable Entity",
            )

        for field, value in update_data.items():
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
