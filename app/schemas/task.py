import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.models.enums import EntityStatus, PriorityLevel


class TaskCreate(BaseModel):
    feature_id: uuid.UUID | None = None
    name: str
    description: str | None = None
    priority: PriorityLevel | None = None
    start_date: date | None = None
    due_date: date | None = None


class TaskUpdate(BaseModel):
    feature_id: uuid.UUID | None = None
    name: str | None = None
    description: str | None = None
    status: EntityStatus | None = None
    priority: PriorityLevel | None = None
    start_date: date | None = None
    due_date: date | None = None


class TaskRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
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
