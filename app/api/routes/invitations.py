import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import generate_refresh_token
from app.models.enums import InvitationStatus, UserRole
from app.models.invitation import Invitation
from app.models.project import ProjectMember
from app.models.user import User
from app.schemas.invitation import InvitationCreate, InvitationRead
from app.schemas.common_response import APIResponse, success_response, COMMON_RESPONSES

router = APIRouter(
    prefix="/invitations",
    tags=["invitations"],
    responses=COMMON_RESPONSES,
)


def _is_active_project_manager(
    db: Session,
    caller: User,
    project_id: uuid.UUID,
) -> bool:
    return (
        db.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == caller.id,
                ProjectMember.removed_at.is_(None),
            )
        )
        is not None
    )


def _authorize_invite_management(
    db: Session,
    caller: User,
    project_id: uuid.UUID,
) -> None:
    if caller.role == UserRole.admin:
        return

    if caller.role == UserRole.manager and _is_active_project_manager(
        db, caller, project_id
    ):
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient permissions",
    )


@router.post(
    "",
    response_model=APIResponse[InvitationRead],
    status_code=status.HTTP_201_CREATED,
)
def create_invitation(
    payload: InvitationCreate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[InvitationRead]:
    _authorize_invite_management(
        db,
        caller,
        payload.project_id,
    )

    if payload.intended_role != UserRole.employee:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Invitations are for employees only; "
                "add managers via /project-members"
            ),
        )

    invitation = Invitation(
        organization_id=caller.organization_id,
        project_id=payload.project_id,
        email=payload.email,
        intended_role=payload.intended_role,
        token=generate_refresh_token(),
        status=InvitationStatus.pending,
        invited_by=caller.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )

    db.add(invitation)
    db.flush()
    db.refresh(invitation)
    db.commit()

    return success_response(
        status_code=status.HTTP_201_CREATED,
        status_message="Invitation created successfully",
        response_data=invitation,
    )


@router.get(
    "",
    response_model=APIResponse[list[InvitationRead]],
)
def list_invitations(
    id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    email: str | None = None,
    status: InvitationStatus | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> APIResponse[list[InvitationRead]]:
    stmt = select(Invitation)

    if id is not None:
        stmt = stmt.where(Invitation.id == id)

    if project_id is not None:
        stmt = stmt.where(Invitation.project_id == project_id)

    if email is not None:
        stmt = stmt.where(Invitation.email == email)

    if status is not None:
        stmt = stmt.where(Invitation.status == status)

    invitations = list(db.scalars(stmt))

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Invitations retrieved successfully",
        response_data=invitations,
    )


@router.post(
    "/{invitation_id}/revoke",
    response_model=APIResponse[InvitationRead],
)
def revoke_invitation(
    invitation_id: uuid.UUID,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[InvitationRead]:
    invitation = db.get(
        Invitation,
        invitation_id,
    )

    if invitation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
        )

    _authorize_invite_management(
        db,
        caller,
        invitation.project_id,
    )

    if invitation.status != InvitationStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Invitation is not pending",
        )

    invitation.status = InvitationStatus.revoked

    db.flush()
    db.refresh(invitation)
    db.commit()

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Invitation revoked successfully",
        response_data=invitation,
    )


@router.post(
    "/{invitation_id}/accept",
    response_model=APIResponse[InvitationRead],
)
def accept_invitation(
    invitation_id: uuid.UUID,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[InvitationRead]:
    invitation = db.get(
        Invitation,
        invitation_id,
    )

    if invitation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
        )

    if caller.email != invitation.email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This invitation is not addressed to your account",
        )

    if (
        invitation.status != InvitationStatus.pending
        or invitation.expires_at <= datetime.now(timezone.utc)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Invitation is expired or no longer pending",
        )

    existing_membership = db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == invitation.project_id,
            ProjectMember.user_id == caller.id,
            ProjectMember.removed_at.is_(None),
        )
    )

    if existing_membership is None:
        db.add(
            ProjectMember(
                organization_id=invitation.organization_id,
                project_id=invitation.project_id,
                user_id=caller.id,
                added_by=invitation.invited_by,
            )
        )

    invitation.status = InvitationStatus.accepted
    invitation.accepted_at = datetime.now(timezone.utc)

    db.flush()
    db.refresh(invitation)
    db.commit()

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Invitation accepted successfully",
        response_data=invitation,
    )
