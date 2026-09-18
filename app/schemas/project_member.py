import uuid
from datetime import datetime

from pydantic import BaseModel


class ProjectMemberCreate(BaseModel):
    project_id: uuid.UUID
    user_id: uuid.UUID


class ProjectMemberRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID
    user_id: uuid.UUID
    added_by: uuid.UUID
    added_at: datetime
    removed_at: datetime | None
    removed_by: uuid.UUID | None

    model_config = {"from_attributes": True}
