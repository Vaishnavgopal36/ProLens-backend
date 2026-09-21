import uuid
from datetime import datetime

from sqlalchemy import func, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, joinedload

from app.models.collaboration import Comment, ProjectDiscussionRead
from app.repositories.base_repository import BaseRepository


class DiscussionRepository(BaseRepository[Comment]):
    model = Comment

    def __init__(self, db: Session):
        super().__init__(db)

    def list_page(
        self,
        *,
        project_id: uuid.UUID,
        limit: int,
        before: tuple[datetime, uuid.UUID] | None = None,
    ) -> list[Comment]:
        """Newest-first keyset page; authors are joined in the same query."""
        stmt = (
            select(Comment)
            .options(joinedload(Comment.author))
            .where(Comment.project_id == project_id, Comment.deleted_at.is_(None))
        )
        if before is not None:
            stmt = stmt.where(tuple_(Comment.created_at, Comment.id) < tuple_(*before))
        stmt = stmt.order_by(Comment.created_at.desc(), Comment.id.desc()).limit(limit)
        return list(self.db.scalars(stmt).unique())

    def get_last_read_at(
        self, *, project_id: uuid.UUID, user_id: uuid.UUID
    ) -> datetime | None:
        return self.db.scalar(
            select(ProjectDiscussionRead.last_read_at).where(
                ProjectDiscussionRead.project_id == project_id,
                ProjectDiscussionRead.user_id == user_id,
            )
        )

    def count_unread(
        self,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        last_read_at: datetime | None,
    ) -> int:
        stmt = select(func.count(Comment.id)).where(
            Comment.project_id == project_id,
            Comment.deleted_at.is_(None),
            Comment.author_id != user_id,
        )
        if last_read_at is not None:
            stmt = stmt.where(Comment.created_at > last_read_at)
        return int(self.db.scalar(stmt) or 0)

    def upsert_read(
        self,
        *,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> datetime:
        """Mark the thread read as of the DATABASE clock, the same clock that
        stamps comments.created_at, so app/DB clock skew can never make a
        message posted just after the read look already read."""
        stmt = (
            insert(ProjectDiscussionRead)
            .values(
                organization_id=organization_id,
                project_id=project_id,
                user_id=user_id,
                last_read_at=func.now(),
            )
            .on_conflict_do_update(
                constraint="uq_discussion_read_user_project",
                set_={"last_read_at": func.now(), "updated_at": func.now()},
            )
            .returning(ProjectDiscussionRead.last_read_at)
        )
        return self.db.execute(stmt).scalar_one()
