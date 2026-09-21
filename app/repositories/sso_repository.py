# app/repositories/sso_repository.py

import uuid

from sqlalchemy import select

from app.models.enums import SSOProvider
from app.models.sso import SSOConnection
from app.models.tenancy import Organization
from app.repositories.base_repository import BaseRepository


class SSORepository(BaseRepository[SSOConnection]):
    model = SSOConnection

    def get_connection_by_domain(self, domain: str) -> SSOConnection | None:
        return self.db.scalar(
            select(SSOConnection)
            .join(Organization, Organization.id == SSOConnection.organization_id)
            .where(Organization.domain == domain)
        )

    def get_connection_by_org_id(self, org_id: uuid.UUID) -> SSOConnection | None:
        return self.db.scalar(
            select(SSOConnection).where(SSOConnection.organization_id == org_id)
        )

    def list_filtered(
        self,
        *,
        id: uuid.UUID | None = None,
        organization_id: uuid.UUID | None = None,
        provider: SSOProvider | None = None,
    ) -> list[SSOConnection]:
        stmt = select(SSOConnection)

        if id is not None:
            stmt = stmt.where(SSOConnection.id == id)
        if organization_id is not None:
            stmt = stmt.where(SSOConnection.organization_id == organization_id)
        if provider is not None:
            stmt = stmt.where(SSOConnection.provider == provider)

        return list(self.db.scalars(stmt))
