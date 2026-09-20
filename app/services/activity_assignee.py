import uuid
from fastapi import HTTPException, status

from app.models.task import ActivityAssignee
from app.models.user import User
from app.repositories.activity_assignee import ActivityAssigneeRepository
from app.schemas.activity_assignee import ActivityAssigneeCreate


class ActivityAssigneeService:

    def __init__(self, repository: ActivityAssigneeRepository):
        self.repo = repository

    def create_assignee(
        self, payload: ActivityAssigneeCreate, caller: User
    ) -> ActivityAssignee:
        activity = self.repo.get_activity_by_id(payload.activity_id)

        if activity is None or activity.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Activity not found",
            )

        existing = self.repo.get_active_assignee(
            activity_id=payload.activity_id, user_id=payload.user_id
        )

        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User already assigned to this activity",
            )

        return self.repo.create(
            organization_id=caller.organization_id,
            activity_id=payload.activity_id,
            user_id=payload.user_id,
            assigned_by=caller.id,
        )

    def list_assignees(
        self,
        assignee_id: uuid.UUID | None = None,
        activity_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> list[ActivityAssignee]:
        return self.repo.list(
            assignee_id=assignee_id,
            activity_id=activity_id,
            user_id=user_id,
        )

    def delete_assignee(self, assignee_id: uuid.UUID, caller: User) -> None:
        assignee = self.repo.get_active_assignee_by_id(assignee_id)

        if assignee is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assignment not found",
            )

        self.repo.soft_delete(assignee=assignee, removed_by=caller.id)