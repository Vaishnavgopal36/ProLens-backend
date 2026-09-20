# app/services/designation_service.py

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.api.deps import assert_same_organization
from app.core.exception import CallerHasNoOrganizationError, DesignationNotFoundError
from app.models.enums import UserRole
from app.models.tenancy import Designation
from app.models.user import User
from app.repositories.designation_repository import DesignationRepository
from app.schemas.designation import DesignationCreate, DesignationUpdate


class DesignationService:
    def __init__(self, db: Session):
        self.db = db
        self.designations = DesignationRepository(db)

    def create_designation(self, caller: User, payload: DesignationCreate) -> Designation:
        if caller.organization_id is None:
            raise CallerHasNoOrganizationError()

        designation = Designation(
            organization_id=caller.organization_id,




        
            name=payload.name,
        )

        return self.designations.add(designation)

    def list_designations(
        self,
        caller: User,
        *,
        id: uuid.UUID | None = None,
        name: str | None = None,
    ) -> list[Designation]:
        organization_id = (
            None if caller.role == UserRole.super_admin else caller.organization_id
        )
        return self.designations.list_filtered(
            id=id, name=name, organization_id=organization_id
        )

    def update_designation(
        self, caller: User, designation_id: uuid.UUID, payload: DesignationUpdate
    ) -> Designation:
        designation = self.designations.get_active_by_id(designation_id)
        if designation is None:
            raise DesignationNotFoundError()

        assert_same_organization(caller, designation.organization_id)

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(designation, field, value)

        self.db.flush()
        self.db.refresh(designation)
        return designation

    def delete_designation(self, caller: User, designation_id: uuid.UUID) -> None:
        designation = self.designations.get_active_by_id(designation_id)
        if designation is None:
            raise DesignationNotFoundError()

        assert_same_organization(caller, designation.organization_id)

        designation.deleted_at = datetime.now(timezone.utc)
        designation.deleted_by = caller.id
        self.db.flush()