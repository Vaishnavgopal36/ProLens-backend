import uuid
from datetime import date, datetime

from pydantic import BaseModel, model_validator


class TimeLogCreate(BaseModel):
    task_id: uuid.UUID | None = None
    activity_id: uuid.UUID | None = None
    log_date: date
    duration_minutes: int
    description: str | None = None

    @model_validator(mode="after")
    def check_exclusive_target(self) -> "TimeLogCreate":
        if bool(self.task_id) == bool(self.activity_id):
            raise ValueError("Exactly one of task_id or activity_id must be set")
        return self


class TimeLogUpdate(BaseModel):
    task_id: uuid.UUID | None = None
    activity_id: uuid.UUID | None = None
    log_date: date | None = None
    duration_minutes: int | None = None
    description: str | None = None


class TimeLogRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    task_id: uuid.UUID | None
    activity_id: uuid.UUID | None
    log_date: date
    duration_minutes: int
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
