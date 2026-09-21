import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

from app.models.enums import EntityStatus, PriorityLevel


def _check_dates(start: date | None, due: date | None) -> None:
    if start is not None and due is not None and start > due:
        raise ValueError("start_date must be on or before due_date")


class TaskCreate(BaseModel):
    project_id: uuid.UUID | None = None
    feature_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10_000)
    priority: PriorityLevel | None = None
    start_date: date | None = None
    due_date: date | None = None

    @model_validator(mode="after")
    def _validate_dates(self) -> "TaskCreate":
        _check_dates(self.start_date, self.due_date)
        return self


class TaskUpdate(BaseModel):
    project_id: uuid.UUID | None = None
    feature_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10_000)
    status: EntityStatus | None = None
    priority: PriorityLevel | None = None
    start_date: date | None = None
    due_date: date | None = None

    @model_validator(mode="after")
    def _validate(self) -> "TaskUpdate":
        for field in ("name", "status", "priority"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        _check_dates(self.start_date, self.due_date)
        return self


class TaskRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID | None
    feature_id: uuid.UUID | None
    name: str
    description: str | None
    status: EntityStatus
    priority: PriorityLevel
    start_date: date | None
    due_date: date | None
    created_by: uuid.UUID
    updated_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
