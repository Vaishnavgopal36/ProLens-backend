import uuid
from datetime import datetime

from pydantic import BaseModel


class TaskAssigneeCreate(BaseModel):
    task_id: uuid.UUID
    user_id: uuid.UUID


class TaskAssigneeRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    task_id: uuid.UUID
    user_id: uuid.UUID
    assigned_by: uuid.UUID
    assigned_at: datetime
    removed_at: datetime | None
    removed_by: uuid.UUID | None

    model_config = {"from_attributes": True}
