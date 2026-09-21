from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import UUID, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import CalendarEventType, LeaveType

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.task import Activity, Task
    from app.models.user import User


class TimeLog(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "time_logs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True
    )
    activity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activities.id"), nullable=True
    )
    log_date: Mapped[date] = mapped_column(Date, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    user: Mapped[User] = relationship(foreign_keys=[user_id])
    task: Mapped[Task | None] = relationship()
    activity: Mapped[Activity | None] = relationship()

    @property
    def project(self) -> Project | None:
        """Time log's project, derived via task/activity (not a stored column).

        project_id is derivable up the task/activity -> feature/project chain;
        storing it directly would duplicate data with no sync mechanism.
        """
        if self.task is not None:
            return self.task.project
        if self.activity is not None:
            return self.activity.project
        return None

    __table_args__ = (
        CheckConstraint("duration_minutes > 0", name="chk_timelog_duration_positive"),
        CheckConstraint(
            "duration_minutes <= 1440", name="chk_timelog_duration_max_24h"
        ),
        CheckConstraint(
            """
            (
                (CASE WHEN task_id IS NOT NULL THEN 1 ELSE 0 END) +
                (CASE WHEN activity_id IS NOT NULL THEN 1 ELSE 0 END)
            ) = 1
            """,
            name="chk_timelog_target_exclusive_arc",
        ),
        Index("idx_timelogs_user_date", "user_id", "log_date"),
        Index("idx_timelogs_org_date", "organization_id", "log_date"),
    )


class LeaveLog(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "leave_logs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    leave_type: Mapped[LeaveType] = mapped_column(
        PgEnum(LeaveType, name="leave_type", create_type=False),
        nullable=False,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    user: Mapped[User] = relationship(foreign_keys=[user_id])

    __table_args__ = (
        # Requires: CREATE EXTENSION IF NOT EXISTS btree_gist; (add as a migration step)
        ExcludeConstraint(
            ("user_id", "="),
            (text("daterange(start_date, end_date, '[]')"), "&&"),
            where=text("deleted_at IS NULL"),
            name="excl_leave_logs_no_overlap",
        ),
        Index("idx_leave_logs_org_date", "organization_id", "start_date", "end_date"),
    )


class CalendarEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "calendar_events"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    source_leave_log_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("leave_logs.id"),
        nullable=True,
        comment="System-generated from a leave log; deleting the leave log soft-deletes this row (LM-04)",
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_type: Mapped[CalendarEventType] = mapped_column(
        PgEnum(CalendarEventType, name="calendar_event_type", create_type=False),
        nullable=False,
    )
    # Intentional upgrade over the locked schema's start_date/end_date (Date):
    # keeps time-of-day precision for events. Not drift, keep as DateTime.
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    # Relationships
    creator: Mapped[User] = relationship(foreign_keys=[created_by])
    source_leave_log: Mapped[LeaveLog | None] = relationship()

    __table_args__ = (
        CheckConstraint("end_time >= start_time", name="chk_calendar_event_timeline"),
        Index(
            "idx_calendar_events_org_dates", "organization_id", "start_time", "end_time"
        ),
    )
