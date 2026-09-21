import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, model_validator


class ProjectMemberCreate(BaseModel):
    project_id: uuid.UUID
    user_id: uuid.UUID | None = None
    email: EmailStr | None = None

    @model_validator(mode="after")
    def check_user_or_email(self) -> "ProjectMemberCreate":
        if self.user_id is None and self.email is None:
            raise ValueError("Either user_id or email must be provided")
        return self


class ProjectMemberRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID
    user_id: uuid.UUID
    user_name: str | None = None
    user_email: str | None = None
    user_role: str | None = None
    designation: str | None = None
    added_by: uuid.UUID
    added_at: datetime
    removed_at: datetime | None
    removed_by: uuid.UUID | None

    model_config = {"from_attributes": True}
