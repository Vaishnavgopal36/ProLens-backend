import uuid
from datetime import date, datetime, timezone
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.timesheet import TimeLog


class TimeLogRepository:

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, time_log_id: uuid.UUID) -> TimeLog | None:
        return self.db.get(TimeLog, time_log_id)

    def get_active_by_id(self, time_log_id: uuid.UUID) -> TimeLog | None:
        time_log = self.get_by_id(time_log_id)
        if time_log is None or time_log.deleted_at is not None:
            return None
        return time_log

    def create(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        task_id: uuid.UUID | None,
        activity_id: uuid.UUID | None,
        log_date: date,
        duration_minutes: int,
        description: str | None,
    ) -> TimeLog:
        time_log = TimeLog(
            organization_id=organization_id,
            user_id=user_id,
            task_id=task_id,
            activity_id=activity_id,
            log_date=log_date,
            duration_minutes=duration_minutes,
            description=description,
        )
        self.db.add(time_log)
        self.db.flush()
        self.db.refresh(time_log)
        self.db.commit()
        return time_log

    def list(
        self,
        log_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        task_id: uuid.UUID | None = None,
        activity_id: uuid.UUID | None = None,
        log_date: date | None = None,
    ) -> list[TimeLog]:
        stmt = select(TimeLog).where(TimeLog.deleted_at.is_(None))

        if log_id is not None:
            stmt = stmt.where(TimeLog.id == log_id)
        if user_id is not None:
            stmt = stmt.where(TimeLog.user_id == user_id)
        if task_id is not None:
            stmt = stmt.where(TimeLog.task_id == task_id)
        if activity_id is not None:
            stmt = stmt.where(TimeLog.activity_id == activity_id)
        if log_date is not None:
            stmt = stmt.where(TimeLog.log_date == log_date)

        return list(self.db.scalars(stmt))

    def update(self, time_log: TimeLog, update_data: dict[str, Any]) -> TimeLog:
        for field, value in update_data.items():
            setattr(time_log, field, value)

        self.db.flush()
        self.db.refresh(time_log)
        self.db.commit()
        return time_log

    def soft_delete(self, time_log: TimeLog, deleted_by: uuid.UUID) -> None:
        time_log.deleted_at = datetime.now(timezone.utc)
        time_log.deleted_by = deleted_by
        self.db.commit()