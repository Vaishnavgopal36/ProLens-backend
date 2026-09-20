import uuid
from datetime import date
from fastapi import HTTPException, status

from app.models.timesheet import TimeLog
from app.models.user import User
from app.repositories.time_log import TimeLogRepository
from app.schemas.time_log import TimeLogCreate, TimeLogUpdate


class TimeLogService:

    def __init__(self, repository: TimeLogRepository):
        self.repo = repository

    def create_time_log(self, payload: TimeLogCreate, caller: User) -> TimeLog:
        return self.repo.create(
            organization_id=caller.organization_id,
            user_id=caller.id,
            task_id=payload.task_id,
            activity_id=payload.activity_id,
            log_date=payload.log_date,
            duration_minutes=payload.duration_minutes,
            description=payload.description,
        )

    def list_time_logs(
        self,
        log_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        task_id: uuid.UUID | None = None,
        activity_id: uuid.UUID | None = None,
        log_date: date | None = None,
    ) -> list[TimeLog]:
        return self.repo.list(
            log_id=log_id,
            user_id=user_id,
            task_id=task_id,
            activity_id=activity_id,
            log_date=log_date,
        )

    def update_time_log(
        self, time_log_id: uuid.UUID, payload: TimeLogUpdate, caller: User
    ) -> TimeLog:
        time_log = self.repo.get_active_by_id(time_log_id)

        if time_log is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Time log not found",
            )

        if time_log.user_id != caller.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

        update_data = payload.model_dump(exclude_unset=True)
        return self.repo.update(time_log, update_data)

    def delete_time_log(self, time_log_id: uuid.UUID, caller: User) -> None:
        time_log = self.repo.get_active_by_id(time_log_id)

        if time_log is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Time log not found",
            )

        if time_log.user_id != caller.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

        self.repo.soft_delete(time_log=time_log, deleted_by=caller.id)