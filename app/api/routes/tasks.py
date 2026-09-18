import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.enums import EntityStatus, PriorityLevel, UserRole
from app.models.project import Feature, ProjectMember
from app.models.task import Task, TaskAssignee
from app.models.user import User
from app.schemas.common_response import APIResponse, success_response, COMMON_RESPONSES
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate

router = APIRouter(
    prefix="/tasks",
    tags=["tasks"],
    responses=COMMON_RESPONSES,
)


def _project_id_for_task(
    db: Session,
    task: Task,
) -> uuid.UUID | None:
    if task.feature_id is None:
        return None

    feature = db.get(
        Feature,
        task.feature_id,
    )

    return feature.project_id if feature else None


def _is_project_member(
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


def _is_active_assignee(
    db: Session,
    task_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    return (
        db.scalar(
            select(TaskAssignee).where(
                TaskAssignee.task_id == task_id,
                TaskAssignee.user_id == user_id,
                TaskAssignee.removed_at.is_(None),
            )
        )
        is not None
    )


def _can_write(
    db: Session,
    caller: User,
    task: Task,
    *,
    for_delete: bool = False,
) -> bool:
    if caller.role == UserRole.admin:
        return True

    if caller.role == UserRole.manager:
        project_id = _project_id_for_task(
            db,
            task,
        )

        if project_id is None:
            return True

        return _is_project_member(
            db,
            project_id,
            caller.id,
        )

    if caller.role == UserRole.employee:
        if _is_active_assignee(
            db,
            task.id,
            caller.id,
        ):
            return True

        if for_delete and task.created_by == caller.id:
            return True

        return False

    return False


@router.post(
    "",
    response_model=APIResponse[TaskRead],
    status_code=status.HTTP_201_CREATED,
)
def create_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[TaskRead]:
    if payload.feature_id is not None:
        feature = db.get(
            Feature,
            payload.feature_id,
        )

        if feature is None or feature.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Feature not found",
            )

        if caller.role == UserRole.manager and not _is_project_member(
            db,
            feature.project_id,
            caller.id,
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a member of this project",
            )

    task = Task(
        organization_id=caller.organization_id,
        feature_id=payload.feature_id,
        name=payload.name,
        description=payload.description,
        priority=payload.priority or PriorityLevel.medium,
        start_date=payload.start_date,
        due_date=payload.due_date,
        created_by=caller.id,
    )

    db.add(task)
    db.flush()
    db.refresh(task)
    db.commit()

    return success_response(
        status_code=status.HTTP_201_CREATED,
        status_message="Task created successfully",
        response_data=task,
    )


@router.get(
    "",
    response_model=APIResponse[list[TaskRead]],
)
def list_tasks(
    id: uuid.UUID | None = None,
    feature_id: uuid.UUID | None = None,
    status: EntityStatus | None = None,
    priority: PriorityLevel | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> APIResponse[list[TaskRead]]:
    stmt = select(Task).where(Task.deleted_at.is_(None))

    if id is not None:
        stmt = stmt.where(Task.id == id)

    if feature_id is not None:
        stmt = stmt.where(Task.feature_id == feature_id)

    if status is not None:
        stmt = stmt.where(Task.status == status)

    if priority is not None:
        stmt = stmt.where(Task.priority == priority)

    tasks = list(db.scalars(stmt))

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Tasks retrieved successfully",
        response_data=tasks,
    )


@router.patch(
    "/{task_id}",
    response_model=APIResponse[TaskRead],
)
def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[TaskRead]:
    task = db.get(
        Task,
        task_id,
    )

    if task is None or task.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    if not _can_write(
        db,
        caller,
        task,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, field, value)

    task.updated_by = caller.id

    db.flush()
    db.refresh(task)
    db.commit()

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Task updated successfully",
        response_data=task,
    )


@router.delete(
    "/{task_id}",
    response_model=APIResponse[None],
    status_code=status.HTTP_200_OK,
)
def delete_task(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[None]:
    task = db.get(
        Task,
        task_id,
    )

    if task is None or task.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    if not _can_write(
        db,
        caller,
        task,
        for_delete=True,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    task.deleted_at = datetime.now(timezone.utc)
    task.deleted_by = caller.id

    db.commit()

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Task deleted successfully",
        response_data=None,
    )
