import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import SSOProvider


class SSOConnectionCreate(BaseModel):
    provider: SSOProvider = SSOProvider.azure_ad
    tenant_id: str
    client_id: str
    client_secret: str


class SSOConnectionUpdate(BaseModel):
    tenant_id: str | None = None
    client_id: str | None = None
    client_secret: str | None = None


class SSOConnectionRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    provider: SSOProvider
    tenant_id: str
    client_id: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SSOSyncResult(BaseModel):
    total_fetched: int
    created: int
    updated: int
