"""add employee designation check constraint

Revision ID: 114124ac3705
Revises: 0929dbb1b059
Create Date: 2026-09-18 15:15:10.867894

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '114124ac3705'
down_revision: Union[str, Sequence[str], None] = '0929dbb1b059'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_check_constraint(
        "ck_users_employee_requires_designation",
        "users",
        "role != 'employee' OR designation_id IS NOT NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "ck_users_employee_requires_designation",
        "users",
        type_="check",
    )