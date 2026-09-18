import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import OrgStatus
from app.models.tenancy import Organization


class OrganizationRepository:

    @staticmethod
    def get_by_id(
        db: Session,
        organization_id: uuid.UUID,
    ) -> Organization | None:
        return db.get(
            Organization,
            organization_id,
        )

    @staticmethod
    def get_by_slug(
        db: Session,
        slug: str,
    ) -> Organization | None:
        return db.scalar(select(Organization).where(Organization.slug == slug))

    @staticmethod
    def list(
        db: Session,
        *,
        organization_id: uuid.UUID | None = None,
        status: OrgStatus | None = None,
    ) -> list[Organization]:
        stmt = select(Organization).where(Organization.deleted_at.is_(None))

        if organization_id is not None:
            stmt = stmt.where(Organization.id == organization_id)

        if status is not None:
            stmt = stmt.where(Organization.status == status)

        return list(db.scalars(stmt))

    @staticmethod
    def create(
        db: Session,
        organization: Organization,
    ) -> Organization:
        db.add(organization)
        db.flush()
        db.refresh(organization)

        return organization

    @staticmethod
    def update(
        db: Session,
        organization: Organization,
    ) -> Organization:
        db.flush()
        db.refresh(organization)

        return organization

    @staticmethod
    def soft_delete(
        db: Session,
        organization: Organization,
        deleted_at,
        deleted_by: uuid.UUID,
    ) -> Organization:
        organization.deleted_at = deleted_at
        organization.deleted_by = deleted_by

        db.flush()
        db.refresh(organization)

        return organization
