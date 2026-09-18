from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import OrgStatus

if TYPE_CHECKING:
    from app.models.user import User


class Organization(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    status: Mapped[OrgStatus] = mapped_column(
        PgEnum(OrgStatus, name="org_status", create_type=False),
        nullable=False,
        default=OrgStatus.active,
    )

    # Relationships
    users: Mapped[list[User]] = relationship(
        back_populates="organization", foreign_keys="User.organization_id"
    )
    designations: Mapped[list[Designation]] = relationship(
        back_populates="organization"
    )


class Designation(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "designations"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Relationships
    organization: Mapped[Organization] = relationship(back_populates="designations")
    users: Mapped[list[User]] = relationship(
        back_populates="designation", foreign_keys="User.designation_id"
    )

    __table_args__ = (
        Index("uq_org_designation", "organization_id", "name", unique=True),
    )
