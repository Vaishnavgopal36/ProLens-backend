import uuid

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.enums import UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    # No minimum: accounts created before the password policy must still log in.
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def _lowercase_email(cls, value: str) -> str:
        return value.lower()


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class CurrentUser(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID | None
    email: str
    role: UserRole


class SSOAuthorizeResponse(BaseModel):
    authorize_url: str
