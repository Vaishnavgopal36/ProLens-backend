import uuid
from datetime import datetime

from pydantic import BaseModel


class ActivityAssigneeCreate(BaseModel):
    activity_id: uuid.UUID
    user_id: uuid.UUID


class ActivityAssigneeRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    activity_id: uuid.UUID
    user_id: uuid.UUID
    assigned_by: uuid.UUID
    assigned_at: datetime
    removed_at: datetime | None
    removed_by: uuid.UUID | None

    model_config = {"from_attributes": True}
