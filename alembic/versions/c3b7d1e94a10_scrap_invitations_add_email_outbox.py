"""scrap invitations, add email_outbox

Revision ID: c3b7d1e94a10
Revises: f0ac6e3a3d90
Create Date: 2026-09-21 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c3b7d1e94a10"
down_revision: Union[str, Sequence[str], None] = "f0ac6e3a3d90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ORG_ID_UUID = "NULLIF(current_setting('app.current_org_id', true), '')::uuid"
ORG_SCOPED_USING = (
    "current_setting('app.is_super_admin', true) = 'true' "
    f"OR organization_id = {ORG_ID_UUID}"
)


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table} "
        f"USING ({ORG_SCOPED_USING}) WITH CHECK ({ORG_SCOPED_USING})"
    )


def upgrade() -> None:
    # Invitations feature scrapped. Dropping the table drops its policy too;
    # the shared user_role enum is intentionally kept.
    op.execute("DROP TABLE IF EXISTS invitations")
    op.execute("DROP TYPE IF EXISTS invitation_status")

    outbox_status = postgresql.ENUM(
        "pending", "processing", "sent", "failed", name="outbox_status"
    )
    outbox_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "email_outbox",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("to_email", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending",
                "processing",
                "sent",
                "failed",
                name="outbox_status",
                create_type=False,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "attempts", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_email_outbox_status_next_attempt",
        "email_outbox",
        ["status", "next_attempt_at"],
    )
    _enable_rls("email_outbox")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON email_outbox")
    op.drop_index("ix_email_outbox_status_next_attempt", table_name="email_outbox")
    op.drop_table("email_outbox")
    postgresql.ENUM(name="outbox_status").drop(op.get_bind(), checkfirst=True)

    postgresql.ENUM(
        "pending", "accepted", "expired", "revoked", name="invitation_status"
    ).create(op.get_bind(), checkfirst=True)
    op.create_table(
        "invitations",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column(
            "intended_role",
            postgresql.ENUM(
                "super_admin",
                "admin",
                "manager",
                "employee",
                name="user_role",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("token", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending",
                "accepted",
                "expired",
                "revoked",
                name="invitation_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("invited_by", sa.UUID(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )
    _enable_rls("invitations")
