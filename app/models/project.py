from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import EntityStatus, ProjectStatus

if TYPE_CHECKING:
    from app.models.task import Activity, Task
    from app.models.user import User


class Project(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "projects"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_name: Mapped[str | None] = mapped_column(String, nullable=True)
    client_contact: Mapped[str | None] = mapped_column(String, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        PgEnum(ProjectStatus, name="project_status", create_type=False),
        nullable=False,
        default=ProjectStatus.active,
    )
    budget: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    # Relationships
    members: Mapped[list[ProjectMember]] = relationship(back_populates="project")
    features: Mapped[list[Feature]] = relationship(back_populates="project")
    activities: Mapped[list[Activity]] = relationship(back_populates="project")
    tasks: Mapped[list[Task]] = relationship(
        secondary="features",
        primaryjoin="Project.id == Feature.project_id",
        secondaryjoin="Feature.id == Task.feature_id",
        viewonly=True,
    )


class ProjectMember(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "project_members"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    added_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    removed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    removed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    # Relationships
    project: Mapped[Project] = relationship(back_populates="members")
    user: Mapped[User] = relationship(foreign_keys=[user_id])

    @property
    def user_name(self) -> str | None:
        if self.user:
            name = f"{self.user.first_name or ''} {self.user.last_name or ''}".strip()
            return name or self.user.email
        return None

    @property
    def user_email(self) -> str | None:
        return self.user.email if self.user else None

    @property
    def user_role(self) -> str | None:
        return self.user.role.value if self.user else None

    @property
    def designation(self) -> str | None:
        return self.user.designation.name if self.user and self.user.designation else None

    __table_args__ = (
        Index(
            "idx_project_members_active",
            "project_id",
            "user_id",
            unique=True,
            postgresql_where=text("removed_at IS NULL"),
        ),
    )


class Feature(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "features"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[EntityStatus] = mapped_column(
        PgEnum(EntityStatus, name="entity_status", create_type=False),
        nullable=False,
        default=EntityStatus.to_do,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    # Relationships
    project: Mapped[Project] = relationship(back_populates="features")
    members: Mapped[list[FeatureMember]] = relationship(back_populates="feature")
    tasks: Mapped[list[Task]] = relationship(back_populates="feature")


class FeatureMember(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "feature_members"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    feature_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("features.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    assigned_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    removed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    removed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    # Relationships
    feature: Mapped[Feature] = relationship(back_populates="members")
    user: Mapped[User] = relationship(foreign_keys=[user_id])

    __table_args__ = (
        Index(
            "idx_feature_members_active",
            "feature_id",
            "user_id",
            unique=True,
            postgresql_where=text("removed_at IS NULL"),
        ),
    )
