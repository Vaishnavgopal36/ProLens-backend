"""azure_ad_integration

Revision ID: cdf452a8d4c2
Revises: 8e69245cfa75
Create Date: 2026-09-15 17:24:43.146993

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cdf452a8d4c2"
down_revision: Union[str, Sequence[str], None] = "8e69245cfa75"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "azure_ad_configs",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("client_secret", sa.String(length=255), nullable=False),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
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
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id"),
    )
    op.execute("ALTER TABLE azure_ad_configs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE azure_ad_configs FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON azure_ad_configs "
        "USING (current_setting('app.is_super_admin', true) = 'true' "
        "OR organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) "
        "WITH CHECK (current_setting('app.is_super_admin', true) = 'true' "
        "OR organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)"
    )

    op.add_column(
        "users", sa.Column("azure_ad_object_id", sa.String(length=36), nullable=True)
    )
    op.alter_column(
        "users", "password_hash", existing_type=sa.VARCHAR(length=255), nullable=True
    )
    op.create_unique_constraint(
        "users_azure_ad_object_id_key", "users", ["azure_ad_object_id"]
    )


def downgrade() -> None:
    op.drop_constraint("users_azure_ad_object_id_key", "users", type_="unique")
    op.alter_column(
        "users", "password_hash", existing_type=sa.VARCHAR(length=255), nullable=False
    )
    op.drop_column("users", "azure_ad_object_id")

    op.execute("DROP POLICY IF EXISTS tenant_isolation ON azure_ad_configs")
    op.execute("ALTER TABLE azure_ad_configs NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE azure_ad_configs DISABLE ROW LEVEL SECURITY")
    op.drop_table("azure_ad_configs")
