from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import SSOProvider


class SSOConnection(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "sso_connections"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, unique=True
    )
    provider: Mapped[SSOProvider] = mapped_column(
        PgEnum(SSOProvider, name="sso_provider", create_type=False),
        nullable=True,
    )
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    client_id: Mapped[str] = mapped_column(String(64), nullable=False)
    client_secret: Mapped[str] = mapped_column(String(255), nullable=False)
