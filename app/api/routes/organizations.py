# app/api/routes/organizations.py

import uuid

from fastapi import APIRouter, Depends
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.pagination import Pagination, get_pagination
from app.core.database import get_db
from app.models.enums import OrgStatus, UserRole
from app.models.user import User
from app.schemas.common_response import APIResponse, success_response
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationRead,
    OrganizationUpdate,
)
from app.services.organization_service import OrganizationService

router = APIRouter(
    prefix="/organizations",
    tags=["organizations"],
)

require_super_admin = require_roles(UserRole.super_admin)


@router.post(
    "",
    response_model=APIResponse[OrganizationRead],
    status_code=http_status.HTTP_201_CREATED,
)
def create_organization(
    payload: OrganizationCreate,
    db: Session = Depends(get_db),
    caller: User = Depends(require_super_admin),
) -> APIResponse[OrganizationRead]:
    org = OrganizationService(db).create_organization(caller, payload)
    db.commit()

    return success_response(
        status_code=http_status.HTTP_201_CREATED,
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
    include_metrics: bool = False,
    include_audit_logs: bool = False,
    pagination: Pagination = Depends(get_pagination),
    db: Session = Depends(get_db),
    _=Depends(require_super_admin),
) -> APIResponse[list[OrganizationRead]]:
    organizations = OrganizationService(db).list_organizations(
        id=id,
        status=status,
        include_metrics=include_metrics,
        include_audit_logs=include_audit_logs,
        limit=pagination.limit,
        offset=pagination.offset,
    )

    return success_response(
        status_code=http_status.HTTP_200_OK,
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
    org = OrganizationService(db).update_organization(org_id, payload)
    db.commit()

    return success_response(
        status_code=http_status.HTTP_200_OK,
        status_message="Organization updated successfully",
        response_data=org,
    )


@router.delete(
    "/{org_id}",
    response_model=APIResponse[None],
    status_code=http_status.HTTP_200_OK,
)
def delete_organization(
    org_id: uuid.UUID,
    db: Session = Depends(get_db),
    caller: User = Depends(require_super_admin),
) -> APIResponse[None]:
    OrganizationService(db).delete_organization(org_id, caller)
    db.commit()

    return success_response(
        status_code=http_status.HTTP_200_OK,
        status_message="Organization deleted successfully",
        response_data=None,
    )
