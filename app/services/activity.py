import uuid
from fastapi import HTTPException, status

from app.models.enums import EntityStatus, UserRole
from app.models.task import Activity
from app.models.user import User
from app.repositories.activity import ActivityRepository
from app.schemas.activity import ActivityCreate, ActivityUpdate


class ActivityService:

    def __init__(self, repository: ActivityRepository):
        self.repo = repository

    def _can_write(self, caller: User, activity: Activity) -> bool:
        if caller.role in (UserRole.admin, UserRole.manager):
            return True

        if caller.role == UserRole.employee:
            if activity.created_by == caller.id:
                return True

            return self.repo.is_active_assignee(
                activity_id=activity.id, user_id=caller.id
            )

        return False

    def create_activity(
        self, payload: ActivityCreate, caller: User
    ) -> Activity:
        return self.repo.create(
            organization_id=caller.organization_id,
            project_id=payload.project_id,
            name=payload.name,
            description=payload.description,
            created_by=caller.id,
        )

    def list_activities(
        self,
        activity_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        status: EntityStatus | None = None,
    ) -> list[Activity]:
        return self.repo.list(
            activity_id=activity_id,
            project_id=project_id,
            status=status,
        )

    def update_activity(
        self, activity_id: uuid.UUID, payload: ActivityUpdate, caller: User
    ) -> Activity:
        activity = self.repo.get_active_by_id(activity_id)

        if activity is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Activity not found",
            )

        if not self._can_write(caller, activity):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

        update_data = payload.model_dump(exclude_unset=True)
        return self.repo.update(
            activity=activity, update_data=update_data, updated_by=caller.id
        )

    def delete_activity(self, activity_id: uuid.UUID, caller: User) -> None:
        activity = self.repo.get_active_by_id(activity_id)

        if activity is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Activity not found",
            )

        if not self._can_write(caller, activity):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

        self.repo.soft_delete(activity=activity, deleted_by=caller.id)