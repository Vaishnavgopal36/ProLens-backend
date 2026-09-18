import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.enums import UserRole
from app.models.project import ProjectMember
from app.models.user import User
from app.schemas.project_member import (
    ProjectMemberCreate,
    ProjectMemberRead,
)
from app.schemas.common_response import APIResponse, success_response, COMMON_RESPONSES

router = APIRouter(
    prefix="/project-members",
    tags=["project-members"],
    responses=COMMON_RESPONSES,
)


def _is_member(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    return (
        db.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
                ProjectMember.removed_at.is_(None),
            )
        )
        is not None
    )


def _authorize_remove(
    db: Session,
    caller: User,
    project_id: uuid.UUID,
    target: User,
) -> None:
    if caller.role == UserRole.admin:
        return

    if (
        caller.role == UserRole.manager
        and target.role == UserRole.employee
        and _is_member(db, project_id, caller.id)
    ):
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient permissions",
    )


@router.post(
    "",
    response_model=APIResponse[ProjectMemberRead],
    status_code=status.HTTP_201_CREATED,
)
def create_project_member(
    payload: ProjectMemberCreate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[ProjectMemberRead]:
    if caller.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Must belong to an organization",
        )

    target = db.get(
        User,
        payload.user_id,
    )

    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if caller.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    if target.role != UserRole.manager:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Only managers can be added directly; "
                "invite employees via /invitations"
            ),
        )

    if _is_member(
        db,
        payload.project_id,
        payload.user_id,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a project member",
        )

    member = ProjectMember(
        organization_id=caller.organization_id,
        project_id=payload.project_id,
        user_id=payload.user_id,
        added_by=caller.id,
    )

    db.add(member)
    db.flush()
    db.refresh(member)
    db.commit()

    return success_response(
        status_code=status.HTTP_201_CREATED,
        status_message="Project member created successfully",
        response_data=member,
    )


@router.get(
    "",
    response_model=APIResponse[list[ProjectMemberRead]],
)
def list_project_members(
    id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> APIResponse[list[ProjectMemberRead]]:
    stmt = select(ProjectMember).where(ProjectMember.removed_at.is_(None))

    if id is not None:
        stmt = stmt.where(ProjectMember.id == id)

    if project_id is not None:
        stmt = stmt.where(ProjectMember.project_id == project_id)

    if user_id is not None:
        stmt = stmt.where(ProjectMember.user_id == user_id)

    members = list(db.scalars(stmt))

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Project members retrieved successfully",
        response_data=members,
    )


@router.delete(
    "/{member_id}",
    response_model=APIResponse[None],
    status_code=status.HTTP_200_OK,
)
def delete_project_member(
    member_id: uuid.UUID,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[None]:
    member = db.get(
        ProjectMember,
        member_id,
    )

    if member is None or member.removed_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project member not found",
        )

    target = db.get(
        User,
        member.user_id,
    )

    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    _authorize_remove(
        db,
        caller,
        member.project_id,
        target,
    )

    member.removed_at = datetime.now(timezone.utc)
    member.removed_by = caller.id

    db.commit()

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Project member deleted successfully",
        response_data=None,
    )
