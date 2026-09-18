"""enable_row_level_security

Revision ID: 8e69245cfa75
Revises: 2d909614fe97
Create Date: 2026-09-15 16:39:41.475110

"""

from typing import Sequence, Union

from alembic import op

revision: str = "8e69245cfa75"
down_revision: Union[str, Sequence[str], None] = "2d909614fe97"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ORG_SCOPED_TABLES = [
    "designations",
    "invitations",
    "projects",
    "project_members",
    "features",
    "feature_members",
    "tasks",
    "task_assignees",
    "activities",
    "activity_assignees",
    "comments",
    "attachments",
    "time_logs",
    "leave_logs",
    "calendar_events",
    "org_insight_snapshots",
    "report_jobs",
    "audit_log",
]

USER_SCOPED_TABLES = [
    "user_preferences",
    "sessions",
]

ORG_ID_UUID = "NULLIF(current_setting('app.current_org_id', true), '')::uuid"
USER_ID_UUID = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"

ORG_SCOPED_USING = (
    "current_setting('app.is_super_admin', true) = 'true' "
    f"OR organization_id = {ORG_ID_UUID}"
)

USER_SCOPED_USING = (
    f"current_setting('app.is_super_admin', true) = 'true' OR user_id = {USER_ID_UUID}"
)

USERS_TABLE_USING = (
    "current_setting('app.is_super_admin', true) = 'true' "
    f"OR id = {USER_ID_UUID} "
    f"OR organization_id = {ORG_ID_UUID}"
)

ORGANIZATIONS_TABLE_USING = (
    f"current_setting('app.is_super_admin', true) = 'true' OR id = {ORG_ID_UUID}"
)


def _enable_rls(table: str, using: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table} "
        f"USING ({using}) WITH CHECK ({using})"
    )


def _disable_rls(table: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")


def upgrade() -> None:
    _enable_rls("organizations", ORGANIZATIONS_TABLE_USING)
    _enable_rls("users", USERS_TABLE_USING)

    for table in ORG_SCOPED_TABLES:
        _enable_rls(table, ORG_SCOPED_USING)

    for table in USER_SCOPED_TABLES:
        _enable_rls(table, USER_SCOPED_USING)


def downgrade() -> None:
    for table in USER_SCOPED_TABLES:
        _disable_rls(table)

    for table in ORG_SCOPED_TABLES:
        _disable_rls(table)

    _disable_rls("users")
    _disable_rls("organizations")
