import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.models.task import ActivityAssignee
from app.repositories.base_repository import BaseRepository


class ActivityAssigneeRepository(BaseRepository[ActivityAssignee]):
    model = ActivityAssignee

    def get_active_assignee(
        self, activity_id: uuid.UUID, user_id: uuid.UUID
    ) -> ActivityAssignee | None:
        return self.db.scalar(
            select(ActivityAssignee).where(
                ActivityAssignee.activity_id == activity_id,
                ActivityAssignee.user_id == user_id,
                ActivityAssignee.removed_at.is_(None),
            )
        )

    def get_active_assignee_by_id(
        self, assignee_id: uuid.UUID
    ) -> ActivityAssignee | None:
        assignee = self.get_by_id(assignee_id)
        if assignee is None or assignee.removed_at is not None:
            return None
        return assignee

    def list_filtered(
        self,
        *,
        limit: int,
        offset: int,
        id: uuid.UUID | None = None,
        activity_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> list[ActivityAssignee]:
        stmt = select(ActivityAssignee).where(ActivityAssignee.removed_at.is_(None))

        if id is not None:
            stmt = stmt.where(ActivityAssignee.id == id)
        if activity_id is not None:
            stmt = stmt.where(ActivityAssignee.activity_id == activity_id)
        if user_id is not None:
            stmt = stmt.where(ActivityAssignee.user_id == user_id)

        stmt = stmt.order_by(ActivityAssignee.assigned_at, ActivityAssignee.id)
        return list(self.db.scalars(stmt.limit(limit).offset(offset)))

    def soft_delete(self, assignee: ActivityAssignee, removed_by: uuid.UUID) -> None:
        assignee.removed_at = datetime.now(timezone.utc)
        assignee.removed_by = removed_by
        self.db.flush()
