import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.models.enums import InvitationStatus, UserRole


class InvitationCreate(BaseModel):
    project_id: uuid.UUID
    email: EmailStr
    intended_role: UserRole


class InvitationRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID
    email: str
    intended_role: UserRole
    status: InvitationStatus
    invited_by: uuid.UUID
    expires_at: datetime
    accepted_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
