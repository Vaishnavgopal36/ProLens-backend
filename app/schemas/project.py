import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import ProjectStatus

NAME_MAX = 255
DESCRIPTION_MAX = 10_000

_Name = Field(min_length=1, max_length=NAME_MAX)
_Description = Field(default=None, max_length=DESCRIPTION_MAX)
_Short = Field(default=None, max_length=255)
_Budget = Field(default=None, ge=0, max_digits=14, decimal_places=2)


def _check_dates(start: date | None, end: date | None) -> None:
    if start is not None and end is not None and start > end:
        raise ValueError("start_date must be on or before end_date")


class ProjectCreate(BaseModel):
    name: str = _Name
    description: str | None = _Description
    client_name: str | None = _Short
    client_contact: str | None = _Short
    start_date: date | None = None
    end_date: date | None = None
    budget: Decimal | None = _Budget

    @model_validator(mode="after")
    def _validate_dates(self) -> "ProjectCreate":
        _check_dates(self.start_date, self.end_date)
        return self


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX)
    description: str | None = _Description
    client_name: str | None = _Short
    client_contact: str | None = _Short
    start_date: date | None = None
    end_date: date | None = None
    status: ProjectStatus | None = None
    budget: Decimal | None = _Budget

    @model_validator(mode="after")
    def _validate(self) -> "ProjectUpdate":
        for field in ("name", "status"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        _check_dates(self.start_date, self.end_date)
        return self


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
