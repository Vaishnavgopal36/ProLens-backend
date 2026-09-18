import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exception import (
    AdminCredentialsIncompleteError,
    DomainAlreadyInUseError,
    OrganizationNotFoundError,
)
from app.models.enums import OrgStatus, UserRole
from app.models.tenancy import Organization
from app.models.user import User
from app.repositories.organization_repository import OrganizationRepository
from app.schemas.organization import OrganizationCreate, OrganizationUpdate
from app.schemas.user import UserCreate
from app.services.user_service import UserService


class OrganizationService:
    def __init__(self, db: Session):
        self.db = db
        self.organizations = OrganizationRepository(db)

    def create_organization(self, caller: User, payload: OrganizationCreate) -> Organization:
        if self.organizations.get_by_domain(payload.domain):
            raise DomainAlreadyInUseError()

        if bool(payload.admin_email) != bool(payload.admin_password):
            raise AdminCredentialsIncompleteError()

        org = Organization(
            name=payload.name,
            domain=payload.domain,
        )
        org = self.organizations.add(org)

        if payload.admin_email and payload.admin_password:
            UserService(self.db).create_user(
                caller,
                UserCreate(
                    email=payload.admin_email,
                    password=payload.admin_password,
                    first_name=payload.admin_first_name,
                    last_name=payload.admin_last_name,
                    role=UserRole.admin,
                    organization_id=org.id,
                ),
            )

        self.db.refresh(org)
        return org

    def list_organizations(
        self,
        *,
        id: uuid.UUID | None = None,
        status: OrgStatus | None = None,
    ) -> list[Organization]:
        return self.organizations.list_filtered(id=id, status=status)

    def update_organization(
        self, org_id: uuid.UUID, payload: OrganizationUpdate
    ) -> Organization:
        org = self.organizations.get_active_by_id(org_id)
        if org is None:
            raise OrganizationNotFoundError()

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(org, field, value)

        self.db.flush()
        self.db.refresh(org)
        return org

    def delete_organization(self, org_id: uuid.UUID, caller: User) -> None:
        org = self.organizations.get_active_by_id(org_id)
        if org is None:
            raise OrganizationNotFoundError()

        org.deleted_at = datetime.now(timezone.utc)
        org.deleted_by = caller.id
        self.db.flush()