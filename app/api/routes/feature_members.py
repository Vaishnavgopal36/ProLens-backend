import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.enums import UserRole
from app.models.project import Feature, FeatureMember, ProjectMember
from app.models.user import User
from app.schemas.feature_member import (
    FeatureMemberCreate,
    FeatureMemberRead,
)
from app.schemas.common_response import APIResponse, success_response

router = APIRouter(
    prefix="/feature-members",
    tags=["feature-members"],
)


def _is_active_project_member(
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


def _ensure_can_manage_members(
    db: Session,
    caller: User,
    feature: Feature,
) -> None:
    if caller.role == UserRole.admin:
        return

    if caller.role == UserRole.manager and _is_active_project_member(
        db,
        feature.project_id,
        caller.id,
    ):
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient permissions",
    )


@router.post(
    "",
    response_model=APIResponse[FeatureMemberRead],
    status_code=status.HTTP_201_CREATED,
)
def create_feature_member(
    payload: FeatureMemberCreate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[FeatureMemberRead]:
    if caller.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    feature = db.get(
        Feature,
        payload.feature_id,
    )

    if feature is None or feature.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feature not found",
        )

    _ensure_can_manage_members(
        db,
        caller,
        feature,
    )

    existing = db.scalar(
        select(FeatureMember).where(
            FeatureMember.feature_id == payload.feature_id,
            FeatureMember.user_id == payload.user_id,
            FeatureMember.removed_at.is_(None),
        )
    )

    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already an active member",
        )

    member = FeatureMember(
        organization_id=caller.organization_id,
        feature_id=payload.feature_id,
        user_id=payload.user_id,
        assigned_by=caller.id,
    )

    db.add(member)
    db.flush()
    db.refresh(member)
    db.commit()

    return success_response(
        status_code=status.HTTP_201_CREATED,
        status_message="Feature member created successfully",
        response_data=member,
    )


@router.get(
    "",
    response_model=APIResponse[list[FeatureMemberRead]],
)
def list_feature_members(
    id: uuid.UUID | None = None,
    feature_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> APIResponse[list[FeatureMemberRead]]:
    stmt = select(FeatureMember).where(FeatureMember.removed_at.is_(None))

    if id is not None:
        stmt = stmt.where(FeatureMember.id == id)

    if feature_id is not None:
        stmt = stmt.where(FeatureMember.feature_id == feature_id)

    if user_id is not None:
        stmt = stmt.where(FeatureMember.user_id == user_id)

    members = list(db.scalars(stmt))

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Feature members retrieved successfully",
        response_data=members,
    )


@router.delete(
    "/{feature_member_id}",
    response_model=APIResponse[None],
    status_code=status.HTTP_200_OK,
)
def delete_feature_member(
    feature_member_id: uuid.UUID,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[None]:
    member = db.get(
        FeatureMember,
        feature_member_id,
    )

    if member is None or member.removed_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feature member not found",
        )

    feature = db.get(
        Feature,
        member.feature_id,
    )

    if feature is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feature not found",
        )

    _ensure_can_manage_members(
        db,
        caller,
        feature,
    )

    member.removed_at = datetime.now(timezone.utc)
    member.removed_by = caller.id

    db.commit()

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Feature member deleted successfully",
        response_data=None,
    )
