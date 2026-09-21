import uuid

from sqlalchemy.orm import Session

from app.api.pagination import Pagination
from app.core.exception import (
    AppException,
    InsufficientPermissionError,
    NotProjectMemberError,
    ProjectNotFoundError,
)
from app.models.enums import EntityStatus, UserRole
from app.models.task import Activity
from app.models.user import User
from app.repositories.activity import ActivityRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.activity import ActivityCreate, ActivityUpdate

ADMIN_ROLES = (UserRole.admin, UserRole.super_admin)


class ActivityNotFoundError(AppException):
    status_code = 404
    status_message = "Not Found"
    default_message = "Activity not found"


def is_admin(user: User) -> bool:
    return user.role in ADMIN_ROLES


class ActivityService:
    def __init__(self, db: Session):
        self.db = db
        self.activities = ActivityRepository(db)
        self.projects = ProjectRepository(db)

    def get_visible_activity(self, activity_id: uuid.UUID, caller: User) -> Activity:
        """Active activity inside the caller's organization, else 404."""
        activity = self.activities.get_active_by_id(activity_id)
        if activity is None or (
            caller.role != UserRole.super_admin
            and activity.organization_id != caller.organization_id
        ):
            raise ActivityNotFoundError()
        return activity

    def can_write(self, caller: User, activity: Activity) -> bool:
        if is_admin(caller):
            return True

        if caller.role == UserRole.manager:
            if activity.project_id is not None:
                return self.projects.is_member(activity.project_id, caller.id)
            return activity.created_by == caller.id

        if caller.role == UserRole.employee:
            return activity.created_by == caller.id or (
                self.activities.is_active_assignee(
                    activity_id=activity.id, user_id=caller.id
                )
            )

        return False

    def _require_write(self, caller: User, activity: Activity) -> None:
        if not self.can_write(caller, activity):
            raise InsufficientPermissionError()

    def create_activity(self, payload: ActivityCreate, caller: User) -> Activity:
        if payload.project_id is not None:
            project = self.projects.get_active_by_id(payload.project_id)
            if project is None or project.organization_id != caller.organization_id:
                raise ProjectNotFoundError()
            if not is_admin(caller) and not self.projects.is_member(
                project.id, caller.id
            ):
                raise NotProjectMemberError()

        activity = Activity(
            organization_id=caller.organization_id,
            project_id=payload.project_id,
            name=payload.name,
            description=payload.description,
            created_by=caller.id,
        )
        return self.activities.add(activity)

    def list_activities(
        self,
        pagination: Pagination,
        activity_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        status_filter: EntityStatus | None = None,
    ) -> list[Activity]:
        return self.activities.list_filtered(
            limit=pagination.limit,
            offset=pagination.offset,
            id=activity_id,
            project_id=project_id,
            status=status_filter,
        )

    def update_activity(
        self, activity_id: uuid.UUID, payload: ActivityUpdate, caller: User
    ) -> Activity:
        activity = self.get_visible_activity(activity_id, caller)
        self._require_write(caller, activity)

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(activity, field, value)
        activity.updated_by = caller.id

        self.db.flush()
        self.db.refresh(activity)
        return activity

    def delete_activity(self, activity_id: uuid.UUID, caller: User) -> None:
        activity = self.get_visible_activity(activity_id, caller)
        self._require_write(caller, activity)
        self.activities.soft_delete(activity, deleted_by=caller.id)
