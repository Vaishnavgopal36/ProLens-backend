import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.collaboration import Comment
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.comment import CommentCreate, CommentRead, CommentUpdate
from app.schemas.common_response import APIResponse, success_response

router = APIRouter(
    prefix="/comments",
    tags=["comments"],
)


@router.post(
    "",
    response_model=APIResponse[CommentRead],
    status_code=status.HTTP_201_CREATED,
)
def create_comment(
    payload: CommentCreate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[CommentRead]:
    comment = Comment(
        organization_id=caller.organization_id,
        author_id=caller.id,
        parent_comment_id=payload.parent_comment_id,
        project_id=payload.project_id,
        feature_id=payload.feature_id,
        task_id=payload.task_id,
        activity_id=payload.activity_id,
        content=payload.content,
    )

    db.add(comment)
    db.flush()
    db.refresh(comment)
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
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> APIResponse[list[CommentRead]]:
    stmt = select(Comment).where(Comment.deleted_at.is_(None))

    if id is not None:
        stmt = stmt.where(Comment.id == id)

    if project_id is not None:
        stmt = stmt.where(Comment.project_id == project_id)

    if feature_id is not None:
        stmt = stmt.where(Comment.feature_id == feature_id)

    if task_id is not None:
        stmt = stmt.where(Comment.task_id == task_id)

    if activity_id is not None:
        stmt = stmt.where(Comment.activity_id == activity_id)

    if author_id is not None:
        stmt = stmt.where(Comment.author_id == author_id)

    comments = list(db.scalars(stmt))

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
) -> APIResponse[CommentRead]:
    comment = db.get(Comment, comment_id)

    if comment is None or comment.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found",
        )

    if caller.id != comment.author_id and caller.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    comment.content = payload.content

    db.flush()
    db.refresh(comment)
    db.commit()

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
) -> APIResponse[None]:
    comment = db.get(Comment, comment_id)

    if comment is None or comment.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found",
        )

    if caller.id != comment.author_id and caller.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    comment.deleted_at = datetime.now(timezone.utc)
    comment.deleted_by = caller.id

    db.commit()

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Comment deleted successfully",
        response_data=None,
    )
