# app/services/designation_service.py

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.api.deps import assert_same_organization
from app.core.exception import (
    AppException,
    CallerHasNoOrganizationError,
    DesignationNotFoundError,
)
from app.models.enums import UserRole
from app.models.tenancy import Designation
from app.models.user import User
from app.repositories.designation_repository import DesignationRepository
from app.schemas.designation import DesignationCreate, DesignationUpdate


class DesignationService:
    def __init__(self, db: Session):
        self.db = db
        self.designations = DesignationRepository(db)

    def _assert_name_free(
        self,
        organization_id: uuid.UUID,
        name: str,
        exclude_id: uuid.UUID | None = None,
    ) -> None:
        # The DB unique index also counts soft-deleted rows, so only a clean
        # 409 for active duplicates is produced here.
        if self.designations.get_active_by_name(organization_id, name, exclude_id):
            raise AppException(
                "A designation with this name already exists",
                status_code=409,
                status_message="Conflict",
            )

    def create_designation(
        self, caller: User, payload: DesignationCreate
    ) -> Designation:
        if caller.organization_id is None:
            raise CallerHasNoOrganizationError()

        self._assert_name_free(caller.organization_id, payload.name)

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
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Designation]:
        organization_id = (
            None if caller.role == UserRole.super_admin else caller.organization_id
        )
        return self.designations.list_filtered(
            id=id,
            name=name,
            organization_id=organization_id,
            limit=limit,
            offset=offset,
        )

    def update_designation(
        self, caller: User, designation_id: uuid.UUID, payload: DesignationUpdate
    ) -> Designation:
        designation = self.designations.get_active_by_id(designation_id)
        if designation is None:
            raise DesignationNotFoundError()

        assert_same_organization(caller, designation.organization_id)

        if payload.name is not None:
            self._assert_name_free(
                designation.organization_id, payload.name, exclude_id=designation.id
            )

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

        if self.designations.count_assigned_users(designation.id) > 0:
            raise AppException(
                "Designation is still assigned to users",
                status_code=409,
                status_message="Conflict",
            )

        designation.deleted_at = datetime.now(timezone.utc)
        designation.deleted_by = caller.id
        self.db.flush()
