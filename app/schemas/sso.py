import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import SSOProvider

class SSOConnectionCreate(BaseModel):
    organization_id: uuid.UUID | None = None   # only used by super_admin
    provider: SSOProvider = SSOProvider.azure_ad


class SSOConnectionRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    provider: SSOProvider
    tenant_id: str | None = None      # null until discovery completes
    created_at: datetime

    model_config = {"from_attributes": True}


class SSOSyncResult(BaseModel):
    total_fetched: int
    created: int
    updated: int

class SSOAuthorizeResponse(BaseModel):
    authorize_url: str