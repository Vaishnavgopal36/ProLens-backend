import re
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.models.enums import OrgStatus
from app.schemas.user import validate_password_policy

_HOSTNAME_LABEL = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    domain: str = Field(min_length=1, max_length=100)
    admin_email: EmailStr | None = None
    admin_password: str | None = None
    admin_first_name: str | None = Field(default=None, max_length=100)
    admin_last_name: str | None = Field(default=None, max_length=100)

    @field_validator("domain")
    @classmethod
    def _normalize_domain(cls, value: str) -> str:
        domain = value.strip().lower().rstrip(".")
        labels = domain.split(".")
        if len(labels) < 2 or not all(_HOSTNAME_LABEL.match(label) for label in labels):
            raise ValueError("domain must be a valid hostname, e.g. example.com")
        return domain

    @field_validator("admin_email")
    @classmethod
    def _lowercase_admin_email(cls, value: str | None) -> str | None:
        return value.lower() if value else value

    @field_validator("admin_password")
    @classmethod
    def _check_admin_password(cls, value: str | None) -> str | None:
        return None if value is None else validate_password_policy(value)


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: OrgStatus | None = None

    @model_validator(mode="after")
    def _reject_nulls(self) -> "OrganizationUpdate":
        for field in ("name", "status"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class OrganizationRead(BaseModel):
    id: uuid.UUID
    name: str
    domain: str
    status: OrgStatus
    active_projects: int | None = None
    total_members: int | None = None
    audit_logs: list[dict] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
