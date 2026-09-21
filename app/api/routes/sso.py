import uuid

from fastapi import APIRouter, Depends
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.database import get_db
from app.models.enums import SSOProvider, UserRole
from app.models.user import User
from app.schemas.common_response import APIResponse, success_response
from app.schemas.sso import (
    SSOConnectionCreate,
    SSOConnectionRead,
    SSOConnectionUpdate,
    SSOSyncResult,
)
from app.services.sso_connection_services import SSOConnectionService

router = APIRouter(
    prefix="/sso-connections",
    tags=["sso"],
)

require_admin = require_roles(UserRole.admin, UserRole.super_admin)


@router.post(
    "",
    response_model=APIResponse[SSOConnectionRead],
    status_code=http_status.HTTP_201_CREATED,
)
def create_connection(
    payload: SSOConnectionCreate,
    db: Session = Depends(get_db),
    caller: User = Depends(require_admin),
) -> APIResponse[SSOConnectionRead]:
    connection = SSOConnectionService(db).create_connection(caller, payload)
    db.commit()

    return success_response(
        status_code=http_status.HTTP_201_CREATED,
        status_message="SSO connection created successfully",
        response_data=connection,
    )


@router.get("", response_model=APIResponse[list[SSOConnectionRead]])
def list_connections(
    id: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
    provider: SSOProvider | None = None,
    db: Session = Depends(get_db),
    caller: User = Depends(require_admin),
) -> APIResponse[list[SSOConnectionRead]]:
    connections = SSOConnectionService(db).list_connections(
        caller, id=id, organization_id=organization_id, provider=provider
    )

    return success_response(
        status_code=http_status.HTTP_200_OK,
        status_message="SSO connections retrieved successfully",
        response_data=connections,
    )


@router.patch("/{connection_id}", response_model=APIResponse[SSOConnectionRead])
def update_connection(
    connection_id: uuid.UUID,
    payload: SSOConnectionUpdate,
    db: Session = Depends(get_db),
    caller: User = Depends(require_admin),
) -> APIResponse[SSOConnectionRead]:
    connection = SSOConnectionService(db).update_connection(
        caller, connection_id, payload
    )
    db.commit()

    return success_response(
        status_code=http_status.HTTP_200_OK,
        status_message="SSO connection updated successfully",
        response_data=connection,
    )


@router.delete(
    "/{connection_id}",
    response_model=APIResponse[None],
    status_code=http_status.HTTP_200_OK,
)
def delete_connection(
    connection_id: uuid.UUID,
    db: Session = Depends(get_db),
    caller: User = Depends(require_admin),
) -> APIResponse[None]:
    SSOConnectionService(db).delete_connection(caller, connection_id)
    db.commit()

    return success_response(
        status_code=http_status.HTTP_200_OK,
        status_message="SSO connection deleted successfully",
        response_data=None,
    )


@router.post("/{connection_id}/sync", response_model=APIResponse[SSOSyncResult])
def sync_users(
    connection_id: uuid.UUID,
    db: Session = Depends(get_db),
    caller: User = Depends(require_admin),
) -> APIResponse[SSOSyncResult]:
    sync_result = SSOConnectionService(db).sync_users(caller, connection_id)
    db.commit()

    return success_response(
        status_code=http_status.HTTP_200_OK,
        status_message="Users synchronized successfully",
        response_data=sync_result,
    )