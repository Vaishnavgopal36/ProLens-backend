import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.pagination import Pagination, get_pagination
from app.core.database import get_db
from app.models.enums import EntityStatus
from app.models.user import User
from app.schemas.activity import ActivityCreate, ActivityRead, ActivityUpdate
from app.schemas.common_response import APIResponse, success_response
from app.services.activity import ActivityService

router = APIRouter(
    prefix="/activities",
    tags=["activities"],
)


def get_activity_service(db: Session = Depends(get_db)) -> ActivityService:
    return ActivityService(db)


@router.post(
    "",
    response_model=APIResponse[ActivityRead],
    status_code=status.HTTP_201_CREATED,
)
def create_activity(
    payload: ActivityCreate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
    service: ActivityService = Depends(get_activity_service),
) -> APIResponse[ActivityRead]:
    activity = service.create_activity(payload=payload, caller=caller)
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
    status_filter: EntityStatus | None = Query(default=None, alias="status"),
    pagination: Pagination = Depends(get_pagination),
    _: User = Depends(get_current_user),
    service: ActivityService = Depends(get_activity_service),
) -> APIResponse[list[ActivityRead]]:
    activities = service.list_activities(
        pagination=pagination,
        activity_id=id,
        project_id=project_id,
        status_filter=status_filter,
    )

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
    service: ActivityService = Depends(get_activity_service),
) -> APIResponse[ActivityRead]:
    activity = service.update_activity(
        activity_id=activity_id, payload=payload, caller=caller
    )
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
    service: ActivityService = Depends(get_activity_service),
) -> APIResponse[None]:
    service.delete_activity(activity_id=activity_id, caller=caller)
    db.commit()

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Activity deleted successfully",
        response_data=None,
    )
