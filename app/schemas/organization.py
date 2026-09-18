import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.models.enums import OrgStatus


class OrganizationCreate(BaseModel):
    name: str
    slug: str
    admin_email: EmailStr | None = None
    admin_password: str | None = None
    admin_first_name: str | None = None
    admin_last_name: str | None = None


class OrganizationUpdate(BaseModel):
    name: str | None = None
    status: OrgStatus | None = None


class OrganizationRead(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    status: OrgStatus
    created_at: datetime

    model_config = {"from_attributes": True}
