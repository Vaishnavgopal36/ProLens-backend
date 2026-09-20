import uuid

from fastapi import APIRouter, Depends
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.enums import EntityStatus, PriorityLevel
from app.models.user import User
from app.schemas.common_response import APIResponse, success_response
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate
from app.services.task_service import TaskService

router = APIRouter(
    prefix="/tasks",
    tags=["tasks"],
)


@router.post("", response_model=APIResponse[TaskRead], status_code=http_status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[TaskRead]:
    task = TaskService(db).create_task(caller, payload)
    db.commit()

    return success_response(
        status_code=http_status.HTTP_201_CREATED,
        status_message="Task created successfully",
        response_data=task,
    )


@router.get("", response_model=APIResponse[list[TaskRead]])
def list_tasks(
    id: uuid.UUID | None = None,
    feature_id: uuid.UUID | None = None,
    status: EntityStatus | None = None,
    priority: PriorityLevel | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> APIResponse[list[TaskRead]]:
    tasks = TaskService(db).list_tasks(id=id, feature_id=feature_id, status=status, priority=priority)

    return success_response(
        status_code=http_status.HTTP_200_OK,
        status_message="Tasks retrieved successfully",
        response_data=tasks,
    )


@router.patch("/{task_id}", response_model=APIResponse[TaskRead])
def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[TaskRead]:
    task = TaskService(db).update_task(caller, task_id, payload)
    db.commit()

    return success_response(
        status_code=http_status.HTTP_200_OK,
        status_message="Task updated successfully",
        response_data=task,
    )


@router.delete("/{task_id}", response_model=APIResponse[None], status_code=http_status.HTTP_200_OK)
def delete_task(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[None]:
    TaskService(db).delete_task(caller, task_id)
    db.commit()

    return success_response(
        status_code=http_status.HTTP_200_OK,
        status_message="Task deleted successfully",
        response_data=None,
    )