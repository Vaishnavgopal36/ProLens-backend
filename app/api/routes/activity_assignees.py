import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.api.pagination import Pagination, get_pagination
from app.core.database import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.activity_assignee import (
    ActivityAssigneeCreate,
    ActivityAssigneeRead,
)
from app.schemas.common_response import APIResponse, success_response
from app.services.activity_assignee import ActivityAssigneeService

router = APIRouter(
    prefix="/activity-assignees",
    tags=["activity-assignees"],
)

require_manager = require_roles(
    UserRole.admin,
    UserRole.manager,
)


def get_activity_assignee_service(
    db: Session = Depends(get_db),
) -> ActivityAssigneeService:
    return ActivityAssigneeService(db)


@router.post(
    "",
    response_model=APIResponse[ActivityAssigneeRead],
    status_code=status.HTTP_201_CREATED,
)
def create_activity_assignee(
    payload: ActivityAssigneeCreate,
    db: Session = Depends(get_db),
    caller: User = Depends(require_manager),
    service: ActivityAssigneeService = Depends(get_activity_assignee_service),
) -> APIResponse[ActivityAssigneeRead]:
    assignee = service.create_assignee(payload=payload, caller=caller)
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
    pagination: Pagination = Depends(get_pagination),
    _: User = Depends(get_current_user),
    service: ActivityAssigneeService = Depends(get_activity_assignee_service),
) -> APIResponse[list[ActivityAssigneeRead]]:
    assignees = service.list_assignees(
        pagination=pagination,
        assignee_id=id,
        activity_id=activity_id,
        user_id=user_id,
    )

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
    service: ActivityAssigneeService = Depends(get_activity_assignee_service),
) -> APIResponse[None]:
    service.delete_assignee(assignee_id=assignee_id, caller=caller)
    db.commit()

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Activity assignee deleted successfully",
        response_data=None,
    )