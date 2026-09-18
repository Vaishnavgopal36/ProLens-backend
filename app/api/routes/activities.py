import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.enums import EntityStatus, UserRole
from app.models.task import Activity, ActivityAssignee
from app.models.user import User
from app.schemas.activity import (
    ActivityCreate,
    ActivityRead,
    ActivityUpdate,
)
from app.schemas.common_response import APIResponse, success_response

router = APIRouter(
    prefix="/activities",
    tags=["activities"]
)


def _is_active_assignee(
    db: Session,
    activity_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    return (
        db.scalar(
            select(ActivityAssignee).where(
                ActivityAssignee.activity_id == activity_id,
                ActivityAssignee.user_id == user_id,
                ActivityAssignee.removed_at.is_(None),
            )
        )
        is not None
    )


def _can_write(
    db: Session,
    caller: User,
    activity: Activity,
) -> bool:
    if caller.role in (UserRole.admin, UserRole.manager):
        return True

    if caller.role == UserRole.employee:
        if activity.created_by == caller.id:
            return True

        return _is_active_assignee(
            db,
            activity.id,
            caller.id,
        )

    return False


@router.post(
    "",
    response_model=APIResponse[ActivityRead],
    status_code=status.HTTP_201_CREATED,
)
def create_activity(
    payload: ActivityCreate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[ActivityRead]:
    activity = Activity(
        organization_id=caller.organization_id,
        project_id=payload.project_id,
        name=payload.name,
        description=payload.description,
        created_by=caller.id,
    )

    db.add(activity)
    db.flush()
    db.refresh(activity)
    db.commit()

    return success_response(
        status_code=status.HTTP_201_CREATED,
        status_message="Activity created successfully",
        response_data=activity,
    )


@router.get(
    "",
    response_model=APIResponse[list[ActivityRead]],
)
def list_activities(
    id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    status: EntityStatus | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> APIResponse[list[ActivityRead]]:
    stmt = select(Activity).where(Activity.deleted_at.is_(None))

    if id is not None:
        stmt = stmt.where(Activity.id == id)

    if project_id is not None:
        stmt = stmt.where(Activity.project_id == project_id)

    if status is not None:
        stmt = stmt.where(Activity.status == status)

    activities = list(db.scalars(stmt))

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Activities retrieved successfully",
        response_data=activities,
    )


@router.patch(
    "/{activity_id}",
    response_model=APIResponse[ActivityRead],
)
def update_activity(
    activity_id: uuid.UUID,
    payload: ActivityUpdate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[ActivityRead]:
    activity = db.get(Activity, activity_id)

    if activity is None or activity.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity not found",
        )

    if not _can_write(db, caller, activity):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(activity, field, value)

    activity.updated_by = caller.id

    db.flush()
    db.refresh(activity)
    db.commit()

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Activity updated successfully",
        response_data=activity,
    )


@router.delete(
    "/{activity_id}",
    response_model=APIResponse[None],
    status_code=status.HTTP_200_OK,
)
def delete_activity(
    activity_id: uuid.UUID,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[None]:
    activity = db.get(Activity, activity_id)

    if activity is None or activity.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity not found",
        )

    if not _can_write(db, caller, activity):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    activity.deleted_at = datetime.now(timezone.utc)
    activity.deleted_by = caller.id

    db.commit()

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Activity deleted successfully",
        response_data=None,
    )
