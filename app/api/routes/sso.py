import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.azure_ad import AzureADClient
from app.core.database import get_db
from app.models.enums import SSOProvider, UserRole, UserStatus
from app.models.sso import SSOConnection
from app.models.user import User
from app.schemas.common_response import APIResponse, success_response 
from app.schemas.sso import (
    SSOConnectionCreate,
    SSOConnectionRead,
    SSOSyncResult,
)

router = APIRouter(
    prefix="/sso-connections",
    tags=["sso"],
     
)

require_admin = require_roles(
    UserRole.admin,
    UserRole.super_admin,
)


def _resolve_organization_id(
    caller: User,
    organization_id: uuid.UUID | None,
) -> uuid.UUID:
    if caller.role == UserRole.super_admin:
        if organization_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="organization_id is required",
            )

        return organization_id

    if organization_id not in (
        None,
        caller.organization_id,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot configure another organization",
        )

    return caller.organization_id


@router.post(
    "",
    response_model=APIResponse[SSOConnectionRead],
    status_code=status.HTTP_201_CREATED,
)
def create_connection(
    payload: SSOConnectionCreate,
    db: Session = Depends(get_db),
    caller: User = Depends(require_admin),
) -> APIResponse[SSOConnectionRead]:
    organization_id = _resolve_organization_id(
        caller,
        payload.organization_id,
    )

    if db.scalar(
        select(SSOConnection).where(SSOConnection.organization_id == organization_id)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization already has a connection",
        )

    connection = SSOConnection(
        organization_id=organization_id,
        provider=payload.provider,
        tenant_id=payload.tenant_id,
        client_id=payload.client_id,
        client_secret=payload.client_secret,
    )

    db.add(connection)
    db.flush()
    db.refresh(connection)
    db.commit()

    return success_response(
        status_code=status.HTTP_201_CREATED,
        status_message="SSO connection created successfully",
        response_data=connection,
    )


@router.get(
    "",
    response_model=APIResponse[list[SSOConnectionRead]],
)
def list_connections(
    id: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
    provider: SSOProvider | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> APIResponse[list[SSOConnectionRead]]:
    stmt = select(SSOConnection)

    if id is not None:
        stmt = stmt.where(SSOConnection.id == id)

    if organization_id is not None:
        stmt = stmt.where(SSOConnection.organization_id == organization_id)

    if provider is not None:
        stmt = stmt.where(SSOConnection.provider == provider)

    connections = list(db.scalars(stmt))

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="SSO connections retrieved successfully",
        response_data=connections,
    )


@router.delete(
    "/{connection_id}",
    response_model=APIResponse[None],
    status_code=status.HTTP_200_OK,
)
def delete_connection(
    connection_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> APIResponse[None]:
    connection = db.get(
        SSOConnection,
        connection_id,
    )

    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )

    db.delete(connection)
    db.commit()

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="SSO connection deleted successfully",
        response_data=None,
    )


def upsert_users_from_directory(
    db: Session,
    organization_id: uuid.UUID,
    directory_users: list[dict],
) -> SSOSyncResult:
    created = 0
    updated = 0

    for entry in directory_users:
        subject_id = entry.get("id")
        email = entry.get("mail") or entry.get("userPrincipalName")

        if not subject_id or not email:
            continue

        user = db.scalar(select(User).where(User.sso_subject_id == subject_id))

        if user is None:
            email_match = db.scalar(select(User).where(User.email == email))
            if email_match is not None and email_match.organization_id not in (
                None,
                organization_id,
            ):
                continue
            user = email_match

        if user is None:
            db.add(
                User(
                    organization_id=organization_id,
                    email=email,
                    sso_subject_id=subject_id,
                    first_name=entry.get("givenName"),
                    last_name=entry.get("surname"),
                    role=UserRole.employee,
                    status=UserStatus.invited,
                )
            )
            created += 1
        else:
            user.sso_subject_id = subject_id
            user.first_name = entry.get("givenName") or user.first_name
            user.last_name = entry.get("surname") or user.last_name
            updated += 1

    db.commit()

    return SSOSyncResult(
        total_fetched=len(directory_users),
        created=created,
        updated=updated,
    )


@router.post(
    "/{connection_id}/sync",
    response_model=APIResponse[SSOSyncResult],
)
def sync_users(
    connection_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> APIResponse[SSOSyncResult]:
    connection = db.get(
        SSOConnection,
        connection_id,
    )

    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )

    if connection.provider != SSOProvider.azure_ad:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported provider for sync",
        )

    client = AzureADClient(
        connection.tenant_id,
        connection.client_id,
        connection.client_secret,
    )

    directory_users = client.list_users()

    sync_result = upsert_users_from_directory(
        db,
        connection.organization_id,
        directory_users,
    )

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Users synchronized successfully",
        response_data=sync_result,
    )
