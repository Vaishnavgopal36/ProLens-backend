import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.models.enums import UserRole, UserStatus


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    first_name: str | None = None
    last_name: str | None = None
    role: UserRole
    designation_id: uuid.UUID | None = None
    organization_id: uuid.UUID | None = None


class UserUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    role: UserRole | None = None
    status: UserStatus | None = None
    designation_id: uuid.UUID | None = None


class UserRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID | None
    designation_id: uuid.UUID | None
    email: str
    first_name: str | None
    last_name: str | None
    role: UserRole
    status: UserStatus
    created_at: datetime

    model_config = {"from_attributes": True}
