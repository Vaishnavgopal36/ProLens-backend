import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import ProjectStatus


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    client_name: str | None = None
    client_contact: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    budget: Decimal | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    client_name: str | None = None
    client_contact: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: ProjectStatus | None = None
    budget: Decimal | None = None


class ProjectRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    description: str | None
    client_name: str | None
    client_contact: str | None
    start_date: date | None
    end_date: date | None
    status: ProjectStatus
    budget: Decimal | None
    created_by: uuid.UUID
    updated_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
