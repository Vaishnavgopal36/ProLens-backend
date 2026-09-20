import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.task import Activity, ActivityAssignee


class ActivityAssigneeRepository:

    def __init__(self, db: Session):
        self.db = db

    def get_activity_by_id(self, activity_id: uuid.UUID) -> Activity | None:
        return self.db.get(Activity, activity_id)

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
        assignee = self.db.get(ActivityAssignee, assignee_id)
        if assignee is None or assignee.removed_at is not None:
            return None
        return assignee

    def create(
        self,
        organization_id: uuid.UUID,
        activity_id: uuid.UUID,
        user_id: uuid.UUID,
        assigned_by: uuid.UUID,
    ) -> ActivityAssignee:
        assignee = ActivityAssignee(
            organization_id=organization_id,
            activity_id=activity_id,
            user_id=user_id,
            assigned_by=assigned_by,
        )
        self.db.add(assignee)
        self.db.flush()
        self.db.refresh(assignee)
        self.db.commit()
        return assignee

    def list(
        self,
        assignee_id: uuid.UUID | None = None,
        activity_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> list[ActivityAssignee]:
        stmt = select(ActivityAssignee).where(
            ActivityAssignee.removed_at.is_(None)
        )

        if assignee_id is not None:
            stmt = stmt.where(ActivityAssignee.id == assignee_id)
        if activity_id is not None:
            stmt = stmt.where(ActivityAssignee.activity_id == activity_id)
        if user_id is not None:
            stmt = stmt.where(ActivityAssignee.user_id == user_id)

        return list(self.db.scalars(stmt))

    def soft_delete(
        self, assignee: ActivityAssignee, removed_by: uuid.UUID
    ) -> None:
        assignee.removed_at = datetime.now(timezone.utc)
        assignee.removed_by = removed_by
        self.db.commit()