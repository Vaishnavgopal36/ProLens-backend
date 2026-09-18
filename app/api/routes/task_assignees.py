import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.enums import UserRole
from app.models.project import Feature, ProjectMember
from app.models.task import Task, TaskAssignee
from app.models.user import User
from app.schemas.common_response import APIResponse, success_response 
from app.schemas.task_assignee import (
    TaskAssigneeCreate,
    TaskAssigneeRead,
)

router = APIRouter(
    prefix="/task-assignees",
    tags=["task-assignees"],
     
)


def _can_manage(
    db: Session,
    caller: User,
    task: Task,
) -> bool:
    if caller.role == UserRole.admin:
        return True

    if caller.role == UserRole.manager:
        if task.feature_id is None:
            return True

        feature = db.get(
            Feature,
            task.feature_id,
        )

        if feature is None:
            return True

        return (
            db.scalar(
                select(ProjectMember).where(
                    ProjectMember.project_id == feature.project_id,
                    ProjectMember.user_id == caller.id,
                    ProjectMember.removed_at.is_(None),
                )
            )
            is not None
        )

    return False


@router.post(
    "",
    response_model=APIResponse[TaskAssigneeRead],
    status_code=status.HTTP_201_CREATED,
)
def create_task_assignee(
    payload: TaskAssigneeCreate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[TaskAssigneeRead]:
    task = db.get(
        Task,
        payload.task_id,
    )

    if task is None or task.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    if not _can_manage(
        db,
        caller,
        task,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    existing = db.scalar(
        select(TaskAssignee).where(
            TaskAssignee.task_id == payload.task_id,
            TaskAssignee.user_id == payload.user_id,
            TaskAssignee.removed_at.is_(None),
        )
    )

    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already assigned to this task",
        )

    assignee = TaskAssignee(
        organization_id=caller.organization_id,
        task_id=payload.task_id,
        user_id=payload.user_id,
        assigned_by=caller.id,
    )

    db.add(assignee)
    db.flush()
    db.refresh(assignee)
    db.commit()

    return success_response(
        status_code=status.HTTP_201_CREATED,
        status_message="Task assignee created successfully",
        response_data=assignee,
    )


@router.get(
    "",
    response_model=APIResponse[list[TaskAssigneeRead]],
)
def list_task_assignees(
    id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> APIResponse[list[TaskAssigneeRead]]:
    stmt = select(TaskAssignee).where(TaskAssignee.removed_at.is_(None))

    if id is not None:
        stmt = stmt.where(TaskAssignee.id == id)

    if task_id is not None:
        stmt = stmt.where(TaskAssignee.task_id == task_id)

    if user_id is not None:
        stmt = stmt.where(TaskAssignee.user_id == user_id)

    assignees = list(db.scalars(stmt))

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Task assignees retrieved successfully",
        response_data=assignees,
    )


@router.delete(
    "/{assignee_id}",
    response_model=APIResponse[None],
    status_code=status.HTTP_200_OK,
)
def delete_task_assignee(
    assignee_id: uuid.UUID,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[None]:
    assignee = db.get(
        TaskAssignee,
        assignee_id,
    )

    if assignee is None or assignee.removed_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found",
        )

    task = db.get(
        Task,
        assignee.task_id,
    )

    if task is None or not _can_manage(
        db,
        caller,
        task,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    assignee.removed_at = datetime.now(timezone.utc)
    assignee.removed_by = caller.id

    db.commit()

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Task assignee deleted successfully",
        response_data=None,
    )
