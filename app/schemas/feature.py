import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.enums import EntityStatus


class FeatureCreate(BaseModel):
    project_id: uuid.UUID
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10_000)


class FeatureUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10_000)
    status: EntityStatus | None = None

    @model_validator(mode="after")
    def _reject_null_required(self) -> "FeatureUpdate":
        for field in ("name", "status"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class FeatureRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None
    status: EntityStatus
    created_by: uuid.UUID
    updated_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
