import uuid

from sqlalchemy import select

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