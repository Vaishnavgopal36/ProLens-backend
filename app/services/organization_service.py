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

    def create_organization(
        self, caller: User, payload: OrganizationCreate
    ) -> Organization:
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
        include_metrics: bool = False,
        include_audit_logs: bool = False,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Organization]:
        from sqlalchemy import func, select
        from app.models.project import Project
        from app.models.ops import AuditLog

        orgs = self.organizations.list_filtered(
            id=id, status=status, limit=limit, offset=offset
        )

        if include_metrics or include_audit_logs:
            for o in orgs:
                if include_metrics:
                    o.active_projects = self.db.scalar(
                        select(func.count(Project.id)).where(
                            Project.organization_id == o.id, Project.deleted_at.is_(None)
                        )
                    ) or 0
                    o.total_members = self.db.scalar(
                        select(func.count(User.id)).where(
                            User.organization_id == o.id, User.deleted_at.is_(None)
                        )
                    ) or 0
                if include_audit_logs:
                    logs = self.db.scalars(
                        select(AuditLog)
                        .where(AuditLog.organization_id == o.id)
                        .order_by(AuditLog.changed_at.desc())
                        .limit(20)
                    ).all()
                    o.audit_logs = [
                        {
                            "id": str(l.id),
                            "action": l.action.value,
                            "table_name": l.table_name,
                            "changed_at": l.changed_at.isoformat(),
                            "user_agent": l.user_agent,
                        }
                        for l in logs
                    ]

        return orgs

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
