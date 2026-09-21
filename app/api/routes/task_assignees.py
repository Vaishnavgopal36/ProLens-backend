import uuid

from fastapi import APIRouter, Depends
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.pagination import Pagination, get_pagination
from app.core.database import get_db
from app.models.user import User
from app.schemas.common_response import APIResponse, success_response
from app.schemas.task_assignee import TaskAssigneeCreate, TaskAssigneeRead
from app.services.task_assignee import TaskAssigneeService

router = APIRouter(
    prefix="/task-assignees",
    tags=["task-assignees"],
)


@router.post(
    "",
    response_model=APIResponse[TaskAssigneeRead],
    status_code=http_status.HTTP_201_CREATED,
)
def create_task_assignee(
    payload: TaskAssigneeCreate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[TaskAssigneeRead]:
    assignee = TaskAssigneeService(db).create_assignee(payload=payload, caller=caller)
    db.commit()

    return success_response(
        status_code=http_status.HTTP_201_CREATED,
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
    pagination: Pagination = Depends(get_pagination),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> APIResponse[list[TaskAssigneeRead]]:
    assignees = TaskAssigneeService(db).list_assignees(
        assignee_id=id,
        task_id=task_id,
        user_id=user_id,
        limit=pagination.limit,
        offset=pagination.offset,
    )

    return success_response(
        status_code=http_status.HTTP_200_OK,
        status_message="Task assignees retrieved successfully",
        response_data=assignees,
    )


@router.delete(
    "/{assignee_id}",
    response_model=APIResponse[None],
    status_code=http_status.HTTP_200_OK,
)
def delete_task_assignee(
    assignee_id: uuid.UUID,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[None]:
    TaskAssigneeService(db).delete_assignee(assignee_id=assignee_id, caller=caller)
    db.commit()

    return success_response(
        status_code=http_status.HTTP_200_OK,
        status_message="Task assignee deleted successfully",
        response_data=None,
    )
