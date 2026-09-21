import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.core.config import settings
from app.models.enums import UserRole, UserStatus

BCRYPT_MAX_BYTES = 72


def validate_password_policy(value: str) -> str:
    """Length policy: PASSWORD_MIN_LENGTH chars, at most 72 bytes (bcrypt limit)."""
    if len(value) < settings.PASSWORD_MIN_LENGTH:
        raise ValueError(
            f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters"
        )
    if len(value.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise ValueError(f"Password must be at most {BCRYPT_MAX_BYTES} bytes")
    return value


class UserCreate(BaseModel):
    email: EmailStr
    password: str | None = None
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    role: UserRole
    designation_id: uuid.UUID | None = None
    designation_name: str | None = Field(default=None, max_length=100)
    organization_id: uuid.UUID | None = None

    @field_validator("email")
    @classmethod
    def _lowercase_email(cls, value: str) -> str:
        return value.lower()

    @field_validator("password")
    @classmethod
    def _check_password(cls, value: str | None) -> str | None:
        return None if value is None else validate_password_policy(value)


class UserUpdate(BaseModel):
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    role: UserRole | None = None
    status: UserStatus | None = None
    designation_id: uuid.UUID | None = None
    # Self-service password change; current_password is required with it.
    password: str | None = None
    current_password: str | None = Field(default=None, max_length=256)

    @field_validator("password")
    @classmethod
    def _check_password(cls, value: str | None) -> str | None:
        return None if value is None else validate_password_policy(value)

    @model_validator(mode="after")
    def _reject_null_required_fields(self) -> "UserUpdate":
        # role/status/password are NOT NULL (or must not be cleared) columns.
        for field in ("role", "status", "password"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


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
