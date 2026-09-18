import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import EntityStatus


class ActivityCreate(BaseModel):
    project_id: uuid.UUID | None = None
    name: str
    description: str | None = None


class ActivityUpdate(BaseModel):
    project_id: uuid.UUID | None = None
    name: str | None = None
    description: str | None = None
    status: EntityStatus | None = None


class ActivityRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID | None
    name: str
    description: str | None
    status: EntityStatus
    created_by: uuid.UUID
    updated_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
