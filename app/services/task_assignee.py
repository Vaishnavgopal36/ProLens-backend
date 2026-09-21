import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exception import (
    AppException,
    CrossOrganizationForbiddenError,
    EmployeeOnLeaveError,
    InsufficientPermissionError,
    MustBelongToOrganizationError,
    ProjectMembershipRequiredError,
    TaskNotFoundError,
    UserNotFoundError,
)
from app.models.enums import UserStatus
from app.models.task import Task, TaskAssignee
from app.models.user import User
from app.repositories.feature_repository import FeatureRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.task_assignee_repository import TaskAssigneeRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.user_repository import UserRepository
from app.schemas.task_assignee import TaskAssigneeCreate
from app.services.task_service import TaskService


class TaskAssigneeService:
    def __init__(self, db: Session):
        self.db = db
        self.assignees = TaskAssigneeRepository(db)
        self.tasks = TaskRepository(db)
        self.features = FeatureRepository(db)
        self.projects = ProjectRepository(db)
        self.users = UserRepository(db)
        self.task_service = TaskService(db)

    def _get_task(self, task_id: uuid.UUID) -> Task:
        task = self.tasks.get_active_by_id(task_id)
        if task is None:
            raise TaskNotFoundError()
        return task

    def _authorize(self, caller: User, task: Task) -> None:
        if not self.task_service.can_manage(caller, task):
            raise InsufficientPermissionError()

    def _get_assignable_user(self, user_id: uuid.UUID, caller: User) -> User:
        user = self.users.get_active_by_id(user_id)

        if user is None or user.status != UserStatus.active:
            raise UserNotFoundError()

        if user.organization_id != caller.organization_id:
            raise CrossOrganizationForbiddenError()

        return user

    def create_assignee(
        self, payload: TaskAssigneeCreate, caller: User
    ) -> TaskAssignee:
        if caller.organization_id is None:
            raise MustBelongToOrganizationError()

        task = self._get_task(payload.task_id)
        self._authorize(caller, task)

        user = self._get_assignable_user(payload.user_id, caller)

        # Tasks without a feature have no project membership requirement.
        if task.feature_id is not None:
            feature = self.features.get_by_id(task.feature_id)
            if feature is not None and not self.projects.is_member(
                feature.project_id, user.id
            ):
                raise ProjectMembershipRequiredError()

        if self.assignees.get_active_by_task_and_user(task.id, user.id) is not None:
            raise self._already_assigned()

        if (
            self.assignees.get_conflicting_leave(
                user.id, task.start_date, task.due_date
            )
            is not None
        ):
            raise EmployeeOnLeaveError()

        try:
            return self.assignees.add(
                TaskAssignee(
                    organization_id=caller.organization_id,
                    task_id=task.id,
                    user_id=user.id,
                    assigned_by=caller.id,
                )
            )
        except IntegrityError:
            # Lost a race against the unique (task, user) active index.
            raise self._already_assigned() from None

    @staticmethod
    def _already_assigned() -> AppException:
        return AppException(
            "User already assigned to this task",
            status_code=409,
            status_message="Conflict",
        )

    def list_assignees(
        self,
        assignee_id: uuid.UUID | None = None,
        task_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TaskAssignee]:
        return self.assignees.list_filtered(
            id=assignee_id, task_id=task_id, user_id=user_id, limit=limit, offset=offset
        )

    def delete_assignee(self, assignee_id: uuid.UUID, caller: User) -> None:
        assignee = self.assignees.get_active_by_id(assignee_id)
        if assignee is None:
            raise AppException(
                "Assignment not found", status_code=404, status_message="Not Found"
            )

        task = self.tasks.get_by_id(assignee.task_id)
        if task is None:
            raise TaskNotFoundError()
        self._authorize(caller, task)

        assignee.removed_at = datetime.now(timezone.utc)
        assignee.removed_by = caller.id
        self.db.flush()
