# app/repositories/organization_repository.py

import uuid

from sqlalchemy import select

from app.models.enums import OrgStatus
from app.models.tenancy import Organization
from app.repositories.base_repository import BaseRepository


class OrganizationRepository(BaseRepository[Organization]):
    model = Organization

    def get_by_domain(self, domain: str) -> Organization | None:
        return self.db.scalar(select(Organization).where(Organization.domain == domain))

    def get_active_by_id(self, org_id: uuid.UUID) -> Organization | None:
        org = self.db.get(Organization, org_id)
        if org is None or org.deleted_at is not None:
            return None
        return org

    def list_filtered(
        self,
        *,
        id: uuid.UUID | None = None,
        status: OrgStatus | None = None,
    ) -> list[Organization]:
        stmt = select(Organization).where(Organization.deleted_at.is_(None))

        if id is not None:
            stmt = stmt.where(Organization.id == id)
        if status is not None:
            stmt = stmt.where(Organization.status == status)

        return list(self.db.scalars(stmt))