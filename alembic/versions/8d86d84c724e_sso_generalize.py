"""sso_generalize

Revision ID: 8d86d84c724e
Revises: cdf452a8d4c2
Create Date: 2026-09-15 17:36:03.667310

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "8d86d84c724e"
down_revision: Union[str, Sequence[str], None] = "cdf452a8d4c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    sa.Enum("azure_ad", name="sso_provider").create(op.get_bind())
    op.rename_table("azure_ad_configs", "sso_connections")
    op.add_column(
        "sso_connections",
        sa.Column(
            "provider",
            postgresql.ENUM("azure_ad", name="sso_provider", create_type=False),
            nullable=False,
            server_default="azure_ad",
        ),
    )
    op.alter_column("sso_connections", "provider", server_default=None)

    op.alter_column("users", "azure_ad_object_id", new_column_name="sso_subject_id")
    op.alter_column("users", "sso_subject_id", type_=sa.String(length=64))
    op.execute(
        "ALTER TABLE users RENAME CONSTRAINT users_azure_ad_object_id_key "
        "TO users_sso_subject_id_key"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE users RENAME CONSTRAINT users_sso_subject_id_key "
        "TO users_azure_ad_object_id_key"
    )
    op.alter_column("users", "sso_subject_id", type_=sa.String(length=36))
    op.alter_column("users", "sso_subject_id", new_column_name="azure_ad_object_id")

    op.drop_column("sso_connections", "provider")
    op.rename_table("sso_connections", "azure_ad_configs")
    sa.Enum("azure_ad", name="sso_provider").drop(op.get_bind())
