import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.pagination import Pagination
from app.core.exception import (
    AppException,
    InsufficientPermissionError,
    UserNotFoundError,
)
from app.models.enums import UserRole, UserStatus
from app.models.task import ActivityAssignee
from app.models.user import User
from app.repositories.activity_assignee import ActivityAssigneeRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.user_repository import UserRepository
from app.schemas.activity_assignee import ActivityAssigneeCreate
from app.services.activity import ActivityService

MANAGER_ROLES = (UserRole.admin, UserRole.super_admin, UserRole.manager)


def _already_assigned() -> AppException:
    return AppException(
        "User already assigned to this activity",
        status_code=409,
        status_message="Conflict",
    )


class ActivityAssigneeService:

    def __init__(self, db: Session):
        self.db = db
        self.assignees = ActivityAssigneeRepository(db)
        self.activities = ActivityService(db)
        self.users = UserRepository(db)
        self.projects = ProjectRepository(db)

    def create_assignee(
        self, payload: ActivityAssigneeCreate, caller: User
    ) -> ActivityAssignee:
        if caller.role not in MANAGER_ROLES:
            raise InsufficientPermissionError()

        activity = self.activities.get_visible_activity(payload.activity_id, caller)
        if not self.activities.can_write(caller, activity):
            raise InsufficientPermissionError()

        user = self.users.get_active_by_id(payload.user_id)
        if (
            user is None
            or user.status != UserStatus.active
            or user.organization_id != activity.organization_id
        ):
            raise UserNotFoundError()

        if activity.project_id is not None and not self.projects.is_member(
            activity.project_id, user.id
        ):
            raise AppException(
                "User is not an active member of the activity's project",
                status_code=422,
                status_message="Unprocessable Entity",
            )

        if self.assignees.get_active_assignee(activity.id, user.id) is not None:
            raise _already_assigned()

        assignee = ActivityAssignee(
            organization_id=activity.organization_id,
            activity_id=activity.id,
            user_id=user.id,
            assigned_by=caller.id,
        )
        try:
            return self.assignees.add(assignee)
        except IntegrityError:
            # Lost a race against the partial unique index.
            raise _already_assigned()

    def list_assignees(
        self,
        pagination: Pagination,
        assignee_id: uuid.UUID | None = None,
        activity_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> list[ActivityAssignee]:
        return self.assignees.list_filtered(
            limit=pagination.limit,
            offset=pagination.offset,
            id=assignee_id,
            activity_id=activity_id,
            user_id=user_id,
        )

    def delete_assignee(self, assignee_id: uuid.UUID, caller: User) -> None:
        if caller.role not in MANAGER_ROLES:
            raise InsufficientPermissionError()

        assignee = self.assignees.get_active_assignee_by_id(assignee_id)
        if assignee is None:
            raise AppException(
                "Assignment not found", status_code=404, status_message="Not Found"
            )

        activity = self.activities.get_visible_activity(assignee.activity_id, caller)
        if not self.activities.can_write(caller, activity):
            raise InsufficientPermissionError()

        self.assignees.soft_delete(assignee, removed_by=caller.id)
