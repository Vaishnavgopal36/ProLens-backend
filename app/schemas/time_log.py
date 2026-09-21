import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TimeLogCreate(BaseModel):
    task_id: uuid.UUID | None = None
    activity_id: uuid.UUID | None = None
    log_date: date
    duration_minutes: int = Field(ge=1, le=1440)
    description: str | None = None

    @model_validator(mode="after")
    def check_exclusive_target(self) -> "TimeLogCreate":
        if (self.task_id is not None) == (self.activity_id is not None):
            raise ValueError("Exactly one of task_id or activity_id must be set")
        return self


class TimeLogUpdate(BaseModel):
    # task_id / activity_id are immutable: changing them would break the
    # exclusive-arc check constraint, so unknown fields are rejected.
    model_config = ConfigDict(extra="forbid")

    log_date: date | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    description: str | None = None

    @model_validator(mode="after")
    def reject_null_for_required_fields(self) -> "TimeLogUpdate":
        for field in ("log_date", "duration_minutes"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


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
