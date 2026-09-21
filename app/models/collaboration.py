from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class Comment(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "comments"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    parent_comment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("comments.id"), nullable=True
    )

    # Exclusive arc targets
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True
    )
    feature_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("features.id"), nullable=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True
    )
    activity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activities.id"), nullable=True
    )

    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    author: Mapped[User] = relationship(foreign_keys=[author_id])
    parent: Mapped[Comment | None] = relationship(
        remote_side="Comment.id", back_populates="replies"
    )
    replies: Mapped[list[Comment]] = relationship(back_populates="parent")

    __table_args__ = (
        CheckConstraint(
            """
            (
                (CASE WHEN project_id IS NOT NULL THEN 1 ELSE 0 END) +
                (CASE WHEN feature_id IS NOT NULL THEN 1 ELSE 0 END) +
                (CASE WHEN task_id IS NOT NULL THEN 1 ELSE 0 END) +
                (CASE WHEN activity_id IS NOT NULL THEN 1 ELSE 0 END)
            ) = 1
            """,
            name="chk_comment_target_exclusive_arc",
        ),
        Index("idx_comments_project", "project_id"),
        Index("idx_comments_feature", "feature_id"),
        Index("idx_comments_task", "task_id"),
        Index("idx_comments_activity", "activity_id"),
        Index(
            "idx_comments_project_thread",
            "project_id",
            text("created_at DESC"),
            text("id DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class Attachment(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "attachments"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    # Exclusive arc targets
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True
    )
    feature_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("features.id"), nullable=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True
    )
    activity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activities.id"), nullable=True
    )

    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    s3_key: Mapped[str] = mapped_column(String(500), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)

    # Relationships
    uploader: Mapped[User] = relationship(foreign_keys=[uploaded_by])

    __table_args__ = (
        CheckConstraint(
            """
            (
                (CASE WHEN project_id IS NOT NULL THEN 1 ELSE 0 END) +
                (CASE WHEN feature_id IS NOT NULL THEN 1 ELSE 0 END) +
                (CASE WHEN task_id IS NOT NULL THEN 1 ELSE 0 END) +
                (CASE WHEN activity_id IS NOT NULL THEN 1 ELSE 0 END)
            ) = 1
            """,
            name="chk_attachment_target_exclusive_arc",
        ),
        Index("idx_attachments_project", "project_id"),
        Index("idx_attachments_feature", "feature_id"),
        Index("idx_attachments_task", "task_id"),
        Index("idx_attachments_activity", "activity_id"),
    )


class ProjectDiscussionRead(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Per-user read marker for a project's discussion thread."""

    __tablename__ = "project_discussion_reads"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    last_read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "project_id", name="uq_discussion_read_user_project"
        ),
    )
