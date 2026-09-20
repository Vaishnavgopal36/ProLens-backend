import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.repositories.task_assignee import TaskAssigneeRepository
from app.schemas.common_response import APIResponse, success_response
from app.schemas.task_assignee import TaskAssigneeCreate, TaskAssigneeRead
from app.services.task_assignee import TaskAssigneeService

router = APIRouter(
    prefix="/task-assignees",
    tags=["task-assignees"],
)


def get_task_assignee_service(
    db: Session = Depends(get_db),
) -> TaskAssigneeService:
    repository = TaskAssigneeRepository(db)
    return TaskAssigneeService(repository)


@router.post(
    "",
    response_model=APIResponse[TaskAssigneeRead],
    status_code=status.HTTP_201_CREATED,
)
def create_task_assignee(
    payload: TaskAssigneeCreate,
    caller: User = Depends(get_current_user),
    service: TaskAssigneeService = Depends(get_task_assignee_service),
) -> APIResponse[TaskAssigneeRead]:
    assignee = service.create_assignee(payload=payload, caller=caller)

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
    _: User = Depends(get_current_user),
    service: TaskAssigneeService = Depends(get_task_assignee_service),
) -> APIResponse[list[TaskAssigneeRead]]:
    assignees = service.list_assignees(
        assignee_id=id, task_id=task_id, user_id=user_id
    )

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
    caller: User = Depends(get_current_user),
    service: TaskAssigneeService = Depends(get_task_assignee_service),
) -> APIResponse[None]:
    service.delete_assignee(assignee_id=assignee_id, caller=caller)

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Task assignee deleted successfully",
        response_data=None,
    )