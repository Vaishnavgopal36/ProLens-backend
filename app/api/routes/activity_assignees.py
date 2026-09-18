import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.database import get_db
from app.models.enums import UserRole
from app.models.task import Activity, ActivityAssignee
from app.models.user import User
from app.schemas.activity_assignee import (
    ActivityAssigneeCreate,
    ActivityAssigneeRead,
)
from app.schemas.common_response import APIResponse, success_response, COMMON_RESPONSES

router = APIRouter(
    prefix="/activity-assignees",
    tags=["activity-assignees"],
    responses=COMMON_RESPONSES,
)

require_manager = require_roles(
    UserRole.admin,
    UserRole.manager,
)


@router.post(
    "",
    response_model=APIResponse[ActivityAssigneeRead],
    status_code=status.HTTP_201_CREATED,
)
def create_activity_assignee(
    payload: ActivityAssigneeCreate,
    db: Session = Depends(get_db),
    caller: User = Depends(require_manager),
) -> APIResponse[ActivityAssigneeRead]:
    activity = db.get(Activity, payload.activity_id)

    if activity is None or activity.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity not found",
        )

    existing = db.scalar(
        select(ActivityAssignee).where(
            ActivityAssignee.activity_id == payload.activity_id,
            ActivityAssignee.user_id == payload.user_id,
            ActivityAssignee.removed_at.is_(None),
        )
    )

    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already assigned to this activity",
        )

    assignee = ActivityAssignee(
        organization_id=caller.organization_id,
        activity_id=payload.activity_id,
        user_id=payload.user_id,
        assigned_by=caller.id,
    )

    db.add(assignee)
    db.flush()
    db.refresh(assignee)
    db.commit()

    return success_response(
        status_code=status.HTTP_201_CREATED,
        status_message="Activity assignee created successfully",
        response_data=assignee,
    )


@router.get(
    "",
    response_model=APIResponse[list[ActivityAssigneeRead]],
)
def list_activity_assignees(
    id: uuid.UUID | None = None,
    activity_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> APIResponse[list[ActivityAssigneeRead]]:
    stmt = select(ActivityAssignee).where(ActivityAssignee.removed_at.is_(None))

    if id is not None:
        stmt = stmt.where(ActivityAssignee.id == id)

    if activity_id is not None:
        stmt = stmt.where(ActivityAssignee.activity_id == activity_id)

    if user_id is not None:
        stmt = stmt.where(ActivityAssignee.user_id == user_id)

    assignees = list(db.scalars(stmt))

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Activity assignees retrieved successfully",
        response_data=assignees,
    )


@router.delete(
    "/{assignee_id}",
    response_model=APIResponse[None],
    status_code=status.HTTP_200_OK,
)
def delete_activity_assignee(
    assignee_id: uuid.UUID,
    db: Session = Depends(get_db),
    caller: User = Depends(require_manager),
) -> APIResponse[None]:
    assignee = db.get(ActivityAssignee, assignee_id)

    if assignee is None or assignee.removed_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found",
        )

    assignee.removed_at = datetime.now(timezone.utc)
    assignee.removed_by = caller.id

    db.commit()

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Activity assignee deleted successfully",
        response_data=None,
    )
