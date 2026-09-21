import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import EntityStatus


class ActivityCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class ActivityUpdate(BaseModel):
    # An activity can not be moved between projects, so project_id is rejected.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: EntityStatus | None = None

    @model_validator(mode="after")
    def reject_null_for_required_fields(self) -> "ActivityUpdate":
        for field in ("name", "status"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


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
