import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.collaboration import Comment
from app.models.project import Feature, Project
from app.models.task import Activity, Task
from app.repositories.base_repository import BaseRepository


def load_target(
    db: Session,
    *,
    project_id: uuid.UUID | None = None,
    feature_id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None,
    activity_id: uuid.UUID | None = None,
) -> Project | Feature | Task | Activity | None:
    """RLS-scoped load of whichever exclusive-arc target was supplied.

    Returns None when the row is missing or soft-deleted. The caller still has
    to compare organization_id (FKs bypass RLS, super admins bypass it too).
    """
    for model, target_id in (
        (Project, project_id),
        (Feature, feature_id),
        (Task, task_id),
        (Activity, activity_id),
    ):
        if target_id is not None:
            target = db.get(model, target_id)
            if target is None or target.deleted_at is not None:
                return None
            return target
    return None


class CommentRepository(BaseRepository[Comment]):
    model = Comment

    def get_active_by_id(self, comment_id: uuid.UUID) -> Comment | None:
        comment = self.get_by_id(comment_id)
        if comment is None or comment.deleted_at is not None:
            return None
        return comment

    def list_filtered(
        self,
        *,
        limit: int,
        offset: int,
        id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        feature_id: uuid.UUID | None = None,
        task_id: uuid.UUID | None = None,
        activity_id: uuid.UUID | None = None,
        author_id: uuid.UUID | None = None,
    ) -> list[Comment]:
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

        stmt = stmt.order_by(Comment.created_at, Comment.id)
        return list(self.db.scalars(stmt.limit(limit).offset(offset)))

    def soft_delete(self, comment: Comment, deleted_by: uuid.UUID) -> None:
        comment.deleted_at = datetime.now(timezone.utc)
        comment.deleted_by = deleted_by
        self.db.flush()
