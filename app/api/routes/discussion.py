import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.common_response import APIResponse, success_response
from app.schemas.discussion import (
    DiscussionCreate,
    DiscussionMessage,
    DiscussionPage,
    ReadMarker,
    UnreadRead,
)
from app.services import discussion_events
from app.services.discussion_service import DiscussionService

router = APIRouter(
    prefix="/projects/{project_id}/discussion",
    tags=["discussion"],
)


def get_discussion_service(db: Session = Depends(get_db)) -> DiscussionService:
    return DiscussionService(db)


@router.get("", response_model=APIResponse[DiscussionPage])
def list_discussion(
    project_id: uuid.UUID,
    limit: int = Query(30, ge=1, le=100),
    before: str | None = None,
    caller: User = Depends(get_current_user),
    service: DiscussionService = Depends(get_discussion_service),
) -> APIResponse[DiscussionPage]:
    page = service.list_messages(project_id, caller, limit=limit, before=before)
    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Discussion retrieved successfully",
        response_data=page,
    )


@router.post(
    "",
    response_model=APIResponse[DiscussionMessage],
    status_code=status.HTTP_201_CREATED,
)
def post_message(
    project_id: uuid.UUID,
    payload: DiscussionCreate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
    service: DiscussionService = Depends(get_discussion_service),
) -> APIResponse[DiscussionMessage]:
    message = service.post_message(project_id, payload, caller)
    db.commit()
    discussion_events.publish_event(
        project_id, discussion_events.message_event("message.created", message)
    )
    return success_response(
        status_code=status.HTTP_201_CREATED,
        status_message="Message posted successfully",
        response_data=message,
    )


@router.get("/unread", response_model=APIResponse[UnreadRead])
def get_unread(
    project_id: uuid.UUID,
    caller: User = Depends(get_current_user),
    service: DiscussionService = Depends(get_discussion_service),
) -> APIResponse[UnreadRead]:
    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Unread count retrieved successfully",
        response_data=service.unread(project_id, caller),
    )


@router.post("/read", response_model=APIResponse[ReadMarker])
def mark_read(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
    service: DiscussionService = Depends(get_discussion_service),
) -> APIResponse[ReadMarker]:
    marker = service.mark_read(project_id, caller)
    db.commit()
    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Discussion marked as read",
        response_data=marker,
    )
