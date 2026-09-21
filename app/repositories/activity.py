import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.models.enums import EntityStatus
from app.models.task import Activity, ActivityAssignee
from app.repositories.base_repository import BaseRepository


class ActivityRepository(BaseRepository[Activity]):
    model = Activity

    def get_active_by_id(self, activity_id: uuid.UUID) -> Activity | None:
        activity = self.get_by_id(activity_id)
        if activity is None or activity.deleted_at is not None:
            return None
        return activity

    def is_active_assignee(self, activity_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        return (
            self.db.scalar(
                select(ActivityAssignee.id).where(
                    ActivityAssignee.activity_id == activity_id,
                    ActivityAssignee.user_id == user_id,
                    ActivityAssignee.removed_at.is_(None),
                )
            )
            is not None
        )

    def list_filtered(
        self,
        *,
        limit: int,
        offset: int,
        id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        status: EntityStatus | None = None,
    ) -> list[Activity]:
        stmt = select(Activity).where(Activity.deleted_at.is_(None))

        if id is not None:
            stmt = stmt.where(Activity.id == id)
        if project_id is not None:
            stmt = stmt.where(Activity.project_id == project_id)
        if status is not None:
            stmt = stmt.where(Activity.status == status)

        stmt = stmt.order_by(Activity.created_at, Activity.id)
        return list(self.db.scalars(stmt.limit(limit).offset(offset)))

    def soft_delete(self, activity: Activity, deleted_by: uuid.UUID) -> None:
        activity.deleted_at = datetime.now(timezone.utc)
        activity.deleted_by = deleted_by
        self.db.flush()
