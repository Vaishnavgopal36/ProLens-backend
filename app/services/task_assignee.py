import uuid
from fastapi import HTTPException, status
from app.core.exception import EmployeeOnLeaveError  

from app.models.enums import UserRole
from app.models.task import Task, TaskAssignee
from app.models.user import User
from app.repositories.task_assignee import TaskAssigneeRepository
from app.schemas.task_assignee import TaskAssigneeCreate


class TaskAssigneeService:

    def __init__(self, repository: TaskAssigneeRepository):
        self.repo = repository

    def _can_manage(self, caller: User, task: Task) -> bool:
        if caller.role == UserRole.admin:
            return True

        if caller.role == UserRole.manager:
            if task.feature_id is None:
                return True

            feature = self.repo.get_feature_by_id(task.feature_id)
            if feature is None:
                return True

            return self.repo.is_project_member(
                project_id=feature.project_id, user_id=caller.id
            )

        return False


    def create_assignee(
        self, payload: TaskAssigneeCreate, caller: User
    ) -> TaskAssignee:
        task = self.repo.get_task_by_id(payload.task_id)

        if task is None or task.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found",
            )

        if not self._can_manage(caller, task):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

        if task.due_date is not None:
            conflict = self.repo.get_conflicting_leave(payload.user_id, task.due_date)
            if conflict is not None:
                raise EmployeeOnLeaveError()

        existing = self.repo.get_active_assignee(
            task_id=payload.task_id, user_id=payload.user_id
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User already assigned to this task",
            )

        return self.repo.create(
            organization_id=caller.organization_id,
            task_id=payload.task_id,
            user_id=payload.user_id,
            assigned_by=caller.id,
        )

    def list_assignees(
        self,
        assignee_id: uuid.UUID | None = None,
        task_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> list[TaskAssignee]:
        return self.repo.list(
            assignee_id=assignee_id, task_id=task_id, user_id=user_id
        )

    def delete_assignee(self, assignee_id: uuid.UUID, caller: User) -> None:
        assignee = self.repo.get_active_assignee_by_id(assignee_id)

        if assignee is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assignment not found",
            )

        task = self.repo.get_task_by_id(assignee.task_id)

        if task is None or not self._can_manage(caller, task):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

        self.repo.soft_delete(assignee=assignee, removed_by=caller.id)