import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.routes.users import build_user
from app.core.database import get_db
from app.models.enums import OrgStatus, UserRole
from app.models.tenancy import Organization
from app.models.user import User
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationRead,
    OrganizationUpdate,
)
from app.schemas.user import UserCreate
from app.schemas.common_response import APIResponse, success_response, COMMON_RESPONSES

router = APIRouter(
    prefix="/organizations",
    tags=["organizations"],
    responses=COMMON_RESPONSES,
)

require_super_admin = require_roles(UserRole.super_admin)


@router.post(
    "",
    response_model=APIResponse[OrganizationRead],
    status_code=status.HTTP_201_CREATED,
)
def create_organization(
    payload: OrganizationCreate,
    db: Session = Depends(get_db),
    _=Depends(require_super_admin),
) -> APIResponse[OrganizationRead]:
    if db.scalar(select(Organization).where(Organization.slug == payload.slug)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Slug already in use",
        )

    if bool(payload.admin_email) != bool(payload.admin_password):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=("admin_email and admin_password " "must be provided together"),
        )

    org = Organization(
        name=payload.name,
        slug=payload.slug,
    )

    db.add(org)
    db.flush()

    if payload.admin_email and payload.admin_password:
        admin = build_user(
            db,
            org.id,
            UserCreate(
                email=payload.admin_email,
                password=payload.admin_password,
                first_name=payload.admin_first_name,
                last_name=payload.admin_last_name,
                role=UserRole.admin,
            ),
        )

        db.add(admin)
        db.flush()

    db.refresh(org)
    db.commit()

    return success_response(
        status_code=status.HTTP_201_CREATED,
        status_message="Organization created successfully",
        response_data=org,
    )


@router.get(
    "",
    response_model=APIResponse[list[OrganizationRead]],
)
def list_organizations(
    id: uuid.UUID | None = None,
    status: OrgStatus | None = None,
    db: Session = Depends(get_db),
    _=Depends(require_super_admin),
) -> APIResponse[list[OrganizationRead]]:
    stmt = select(Organization).where(Organization.deleted_at.is_(None))

    if id is not None:
        stmt = stmt.where(Organization.id == id)

    if status is not None:
        stmt = stmt.where(Organization.status == status)

    organizations = list(db.scalars(stmt))

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Organizations retrieved successfully",
        response_data=organizations,
    )


@router.patch(
    "/{org_id}",
    response_model=APIResponse[OrganizationRead],
)
def update_organization(
    org_id: uuid.UUID,
    payload: OrganizationUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_super_admin),
) -> APIResponse[OrganizationRead]:
    org = db.get(
        Organization,
        org_id,
    )

    if org is None or org.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(org, field, value)

    db.flush()
    db.refresh(org)
    db.commit()

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Organization updated successfully",
        response_data=org,
    )


@router.delete(
    "/{org_id}",
    response_model=APIResponse[None],
    status_code=status.HTTP_200_OK,
)
def delete_organization(
    org_id: uuid.UUID,
    db: Session = Depends(get_db),
    caller: User = Depends(require_super_admin),
) -> APIResponse[None]:
    org = db.get(
        Organization,
        org_id,
    )

    if org is None or org.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    org.deleted_at = datetime.now(timezone.utc)
    org.deleted_by = caller.id

    db.commit()

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Organization deleted successfully",
        response_data=None,
    )
