import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.pagination import Pagination, get_pagination
from app.core.database import get_db
from app.models.user import User
from app.schemas.comment import CommentCreate, CommentRead, CommentUpdate
from app.schemas.common_response import APIResponse, success_response
from app.services import discussion_events
from app.services.comment_service import CommentService

router = APIRouter(
    prefix="/comments",
    tags=["comments"],
)


def get_comment_service(db: Session = Depends(get_db)) -> CommentService:
    return CommentService(db)


@router.post(
    "",
    response_model=APIResponse[CommentRead],
    status_code=status.HTTP_201_CREATED,
)
def create_comment(
    payload: CommentCreate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
    service: CommentService = Depends(get_comment_service),
) -> APIResponse[CommentRead]:
    comment = service.create_comment(payload=payload, caller=caller)
    db.commit()

    return success_response(
        status_code=status.HTTP_201_CREATED,
        status_message="Comment created successfully",
        response_data=comment,
    )


@router.get(
    "",
    response_model=APIResponse[list[CommentRead]],
)
def list_comments(
    id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    feature_id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None,
    activity_id: uuid.UUID | None = None,
    author_id: uuid.UUID | None = None,
    pagination: Pagination = Depends(get_pagination),
    _: User = Depends(get_current_user),
    service: CommentService = Depends(get_comment_service),
) -> APIResponse[list[CommentRead]]:
    comments = service.list_comments(
        pagination=pagination,
        comment_id=id,
        project_id=project_id,
        feature_id=feature_id,
        task_id=task_id,
        activity_id=activity_id,
        author_id=author_id,
    )

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Comments retrieved successfully",
        response_data=comments,
    )


@router.patch(
    "/{comment_id}",
    response_model=APIResponse[CommentRead],
)
def update_comment(
    comment_id: uuid.UUID,
    payload: CommentUpdate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
    service: CommentService = Depends(get_comment_service),
) -> APIResponse[CommentRead]:
    comment = service.update_comment(
        comment_id=comment_id, payload=payload, caller=caller
    )
    # Built before commit (attributes are loaded), published only after it succeeds.
    event = discussion_events.build_comment_event("message.updated", comment)
    db.commit()
    discussion_events.publish_event(comment.project_id, event)

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Comment updated successfully",
        response_data=comment,
    )


@router.delete(
    "/{comment_id}",
    response_model=APIResponse[None],
    status_code=status.HTTP_200_OK,
)
def delete_comment(
    comment_id: uuid.UUID,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
    service: CommentService = Depends(get_comment_service),
) -> APIResponse[None]:
    comment = service.delete_comment(comment_id=comment_id, caller=caller)
    project_id = comment.project_id
    event = discussion_events.build_comment_event("message.deleted", comment)
    db.commit()
    discussion_events.publish_event(project_id, event)

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Comment deleted successfully",
        response_data=None,
    )
