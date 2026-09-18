"""global_unique_email

Revision ID: a2f4c324bf70
Revises: ab405c83cdd5
Create Date: 2026-09-15 16:17:26.051196

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a2f4c324bf70"
down_revision: Union[str, Sequence[str], None] = "ab405c83cdd5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(
        op.f("idx_superadmin_email"),
        table_name="users",
        postgresql_where="(organization_id IS NULL)",
    )
    op.drop_index(
        op.f("idx_users_org_email"),
        table_name="users",
        postgresql_where="(organization_id IS NOT NULL)",
    )
    op.create_unique_constraint("users_email_key", "users", ["email"])


def downgrade() -> None:
    op.drop_constraint("users_email_key", "users", type_="unique")
    op.create_index(
        op.f("idx_users_org_email"),
        "users",
        ["organization_id", "email"],
        unique=True,
        postgresql_where="(organization_id IS NOT NULL)",
    )
    op.create_index(
        op.f("idx_superadmin_email"),
        "users",
        ["email"],
        unique=True,
        postgresql_where="(organization_id IS NULL)",
    )
