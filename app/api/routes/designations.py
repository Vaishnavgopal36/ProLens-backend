import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.database import get_db
from app.models.enums import UserRole
from app.models.tenancy import Designation
from app.models.user import User
from app.schemas.designation import (
    DesignationCreate,
    DesignationRead,
    DesignationUpdate,
)
from app.schemas.common_response import APIResponse, success_response, COMMON_RESPONSES

router = APIRouter(
    prefix="/designations",
    tags=["designations"],
    responses=COMMON_RESPONSES,
)

require_admin = require_roles(
    UserRole.admin,
    UserRole.super_admin,
)


@router.post(
    "",
    response_model=APIResponse[DesignationRead],
    status_code=status.HTTP_201_CREATED,
)
def create_designation(
    payload: DesignationCreate,
    db: Session = Depends(get_db),
    caller: User = Depends(require_admin),
) -> APIResponse[DesignationRead]:
    if caller.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Must belong to an organization",
        )

    designation = Designation(
        organization_id=caller.organization_id,
        name=payload.name,
    )

    db.add(designation)
    db.flush()
    db.refresh(designation)
    db.commit()

    return success_response(
        status_code=status.HTTP_201_CREATED,
        status_message="Designation created successfully",
        response_data=designation,
    )


@router.get(
    "",
    response_model=APIResponse[list[DesignationRead]],
)
def list_designations(
    id: uuid.UUID | None = None,
    name: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> APIResponse[list[DesignationRead]]:
    stmt = select(Designation).where(Designation.deleted_at.is_(None))

    if id is not None:
        stmt = stmt.where(Designation.id == id)

    if name is not None:
        stmt = stmt.where(Designation.name == name)

    designations = list(db.scalars(stmt))

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Designations retrieved successfully",
        response_data=designations,
    )


@router.patch(
    "/{designation_id}",
    response_model=APIResponse[DesignationRead],
)
def update_designation(
    designation_id: uuid.UUID,
    payload: DesignationUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> APIResponse[DesignationRead]:
    designation = db.get(
        Designation,
        designation_id,
    )

    if designation is None or designation.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Designation not found",
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(designation, field, value)

    db.flush()
    db.refresh(designation)
    db.commit()

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Designation updated successfully",
        response_data=designation,
    )


@router.delete(
    "/{designation_id}",
    response_model=APIResponse[None],
    status_code=status.HTTP_200_OK,
)
def delete_designation(
    designation_id: uuid.UUID,
    db: Session = Depends(get_db),
    caller: User = Depends(require_admin),
) -> APIResponse[None]:
    designation = db.get(
        Designation,
        designation_id,
    )

    if designation is None or designation.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Designation not found",
        )

    designation.deleted_at = datetime.now(timezone.utc)
    designation.deleted_by = caller.id

    db.commit()

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Designation deleted successfully",
        response_data=None,
    )
