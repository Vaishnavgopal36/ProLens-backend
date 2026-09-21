import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator


def _strip_name(value: str | None) -> str | None:
    return value.strip() if isinstance(value, str) else value


class DesignationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    _strip = field_validator("name", mode="before")(_strip_name)


class DesignationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)

    _strip = field_validator("name", mode="before")(_strip_name)

    @model_validator(mode="after")
    def _reject_null_name(self) -> "DesignationUpdate":
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name cannot be null")
        return self


class DesignationRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}
