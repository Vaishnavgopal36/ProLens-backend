import uuid
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import EntityStatus
from app.models.task import Activity, ActivityAssignee


class ActivityRepository:

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, activity_id: uuid.UUID) -> Activity | None:
        return self.db.get(Activity, activity_id)

    def get_active_by_id(self, activity_id: uuid.UUID) -> Activity | None:
        activity = self.get_by_id(activity_id)
        if activity is None or activity.deleted_at is not None:
            return None
        return activity

    def is_active_assignee(
        self, activity_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        return (
            self.db.scalar(
                select(ActivityAssignee).where(
                    ActivityAssignee.activity_id == activity_id,
                    ActivityAssignee.user_id == user_id,
                    ActivityAssignee.removed_at.is_(None),
                )
            )
            is not None
        )

    def create(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        name: str,
        description: str | None,
        created_by: uuid.UUID,
    ) -> Activity:
        activity = Activity(
            organization_id=organization_id,
            project_id=project_id,
            name=name,
            description=description,
            created_by=created_by,
        )
        self.db.add(activity)
        self.db.flush()
        self.db.refresh(activity)
        self.db.commit()
        return activity

    def list(
        self,
        activity_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        status: EntityStatus | None = None,
    ) -> list[Activity]:
        stmt = select(Activity).where(Activity.deleted_at.is_(None))

        if activity_id is not None:
            stmt = stmt.where(Activity.id == activity_id)
        if project_id is not None:
            stmt = stmt.where(Activity.project_id == project_id)
        if status is not None:
            stmt = stmt.where(Activity.status == status)

        return list(self.db.scalars(stmt))

    def update(
        self,
        activity: Activity,
        update_data: dict[str, Any],
        updated_by: uuid.UUID,
    ) -> Activity:
        for field, value in update_data.items():
            setattr(activity, field, value)

        activity.updated_by = updated_by

        self.db.flush()
        self.db.refresh(activity)
        self.db.commit()
        return activity

    def soft_delete(self, activity: Activity, deleted_by: uuid.UUID) -> None:
        activity.deleted_at = datetime.now(timezone.utc)
        activity.deleted_by = deleted_by
        self.db.commit()