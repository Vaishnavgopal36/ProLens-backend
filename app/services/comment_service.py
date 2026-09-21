import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.api.pagination import Pagination
from app.core.exception import AppException, InsufficientPermissionError
from app.models.collaboration import Comment
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.comment_repository import CommentRepository, load_target
from app.schemas.comment import CommentCreate, CommentUpdate


class CommentNotFoundError(AppException):
    status_code = 404
    status_message = "Not Found"
    default_message = "Comment not found"


class CommentTargetNotFoundError(AppException):
    status_code = 404
    status_message = "Not Found"
    default_message = "Comment target not found"


class CommentService:
    def __init__(self, db: Session):
        self.db = db
        self.comments = CommentRepository(db)

    def _get_comment(self, comment_id: uuid.UUID, caller: User) -> Comment:
        comment = self.comments.get_active_by_id(comment_id)
        if comment is None or (
            caller.role != UserRole.super_admin
            and comment.organization_id != caller.organization_id
        ):
            raise CommentNotFoundError()
        return comment

    def create_comment(self, payload: CommentCreate, caller: User) -> Comment:
        target = load_target(
            self.db,
            project_id=payload.project_id,
            feature_id=payload.feature_id,
            task_id=payload.task_id,
            activity_id=payload.activity_id,
        )
        if target is None or target.organization_id != caller.organization_id:
            raise CommentTargetNotFoundError()

        if payload.parent_comment_id is not None:
            parent = self.comments.get_active_by_id(payload.parent_comment_id)
            if parent is None or parent.organization_id != caller.organization_id:
                raise CommentNotFoundError("Parent comment not found")
            if (
                parent.project_id != payload.project_id
                or parent.feature_id != payload.feature_id
                or parent.task_id != payload.task_id
                or parent.activity_id != payload.activity_id
            ):
                raise AppException(
                    "Parent comment belongs to a different target",
                    status_code=422,
                    status_message="Unprocessable Entity",
                )

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
        return self.comments.add(comment)

    def list_comments(
        self,
        pagination: Pagination,
        comment_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        feature_id: uuid.UUID | None = None,
        task_id: uuid.UUID | None = None,
        activity_id: uuid.UUID | None = None,
        author_id: uuid.UUID | None = None,
    ) -> list[Comment]:
        return self.comments.list_filtered(
            limit=pagination.limit,
            offset=pagination.offset,
            id=comment_id,
            project_id=project_id,
            feature_id=feature_id,
            task_id=task_id,
            activity_id=activity_id,
            author_id=author_id,
        )

    def update_comment(
        self, comment_id: uuid.UUID, payload: CommentUpdate, caller: User
    ) -> Comment:
        comment = self._get_comment(comment_id, caller)

        # Only the author may rewrite a comment, admins included.
        if comment.author_id != caller.id:
            raise InsufficientPermissionError()

        comment.content = payload.content
        comment.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        self.db.refresh(comment)
        return comment

    def delete_comment(self, comment_id: uuid.UUID, caller: User) -> Comment:
        comment = self._get_comment(comment_id, caller)

        if comment.author_id != caller.id and caller.role not in (
            UserRole.admin,
            UserRole.super_admin,
        ):
            raise InsufficientPermissionError()

        self.comments.soft_delete(comment, deleted_by=caller.id)
        return comment
