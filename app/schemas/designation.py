import uuid
from datetime import datetime

from pydantic import BaseModel


class DesignationCreate(BaseModel):
    name: str


class DesignationUpdate(BaseModel):
    name: str | None = None


class DesignationRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}
