from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import AuditAction, HealthStatus, ReportJobStatus, ReportJobType


class OrgInsightSnapshot(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "org_insight_snapshots"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    task_count: Mapped[int] = mapped_column(nullable=False)
    completed_task_count: Mapped[int] = mapped_column(nullable=False)
    estimated_hours_total: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    actual_hours_total: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    time_variance_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    completion_rate_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    health_status: Mapped[HealthStatus | None] = mapped_column(
        PgEnum(HealthStatus, name="health_status", create_type=False), nullable=True
    )
    performance_rank: Mapped[int | None] = mapped_column(nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index("idx_org_insight_snapshots_project_time", "project_id", "computed_at"),
    )

    # Note: append-only — no unique constraint on project_id. The latest row
    # per project by computed_at is "current"; older rows are trend history.
    # An org-wide rollup for the Admin's cross-project ranking view (which
    # Manager's insights deliberately exclude) belongs in a separate table
    # (e.g. org_wide_insight_snapshots) that aggregates these, not here.


class ReportJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "report_jobs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    job_type: Mapped[ReportJobType] = mapped_column(
        PgEnum(ReportJobType, name="report_job_type", create_type=False),
        nullable=False,
    )
    status: Mapped[ReportJobStatus] = mapped_column(
        PgEnum(ReportJobStatus, name="report_job_status", create_type=False),
        nullable=False,
        default=ReportJobStatus.pending,
    )
    parameters: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    result_s3_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("idx_report_jobs_org_status", "organization_id", "status"),
        Index("idx_report_jobs_requested_by", "requested_by"),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    # bigserial PK — high-volume, insert-only log; UUID overhead not worth it here.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True
    )
    table_name: Mapped[str] = mapped_column(String(100), nullable=False)
    record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[AuditAction] = mapped_column(
        PgEnum(AuditAction, name="audit_action", create_type=False),
        nullable=False,
    )
    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    old_values: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    new_values: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # Addition beyond the locked schema — flagged for the schema doc to catch up.
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index("idx_audit_log_table_record", "table_name", "record_id", "changed_at"),
        Index("idx_audit_log_org_changed_at", "organization_id", "changed_at"),
    )
