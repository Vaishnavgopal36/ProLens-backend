"""change leave logs to two table design

Revision ID: 202020
Revises: f0ac6e3a3d90
Create Date: 2026-09-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "202020"
down_revision = "f0ac6e3a3d90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------------------------------------------------------
    # 1. Enable btree_gist
    #
    # Required by the GiST exclusion constraint because
    # user_id and leave_date use equality operators.
    # ---------------------------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    # ---------------------------------------------------------
    # 2. Remove calendar events generated from leave logs
    #
    # calendar_events.source_leave_log_id references
    # leave_logs.id.
    # ---------------------------------------------------------
    op.execute("""
        DELETE FROM calendar_events
        WHERE source_leave_log_id IS NOT NULL
        """)

    # ---------------------------------------------------------
    # 3. Delete all existing leave-log data
    #
    # Existing leave data belongs to the old design and is
    # intentionally discarded.
    # ---------------------------------------------------------
    op.execute("DELETE FROM leave_logs")

    # ---------------------------------------------------------
    # 4. Remove old indexes if they exist
    # ---------------------------------------------------------
    op.execute("DROP INDEX IF EXISTS idx_leave_logs_user_date")

    op.execute("DROP INDEX IF EXISTS idx_leave_logs_org_date")

    # ---------------------------------------------------------
    # 5. Remove old constraints if they exist
    # ---------------------------------------------------------
    op.execute("""
        ALTER TABLE leave_logs
        DROP CONSTRAINT IF EXISTS chk_leave_logs_duration_period
        """)

    op.execute("""
        ALTER TABLE leave_logs
        DROP CONSTRAINT IF EXISTS chk_leave_logs_valid_date_range
        """)

    # ---------------------------------------------------------
    # 6. Remove old single-table leave fields
    # ---------------------------------------------------------
    op.execute("""
        ALTER TABLE leave_logs
        DROP COLUMN IF EXISTS leave_date
        """)

    op.execute("""
        ALTER TABLE leave_logs
        DROP COLUMN IF EXISTS leave_duration
        """)

    op.execute("""
        ALTER TABLE leave_logs
        DROP COLUMN IF EXISTS half_day_period
        """)

    # ---------------------------------------------------------
    # 7. Remove old PostgreSQL enum types
    # ---------------------------------------------------------
    op.execute("DROP TYPE IF EXISTS leave_duration")

    op.execute("DROP TYPE IF EXISTS half_day_period")

    # ---------------------------------------------------------
    # 8. Ensure parent-level fields exist
    #
    # start_date and end_date already exist in your current DB,
    # but IF NOT EXISTS makes this migration safe if the schema
    # differs between environments.
    # ---------------------------------------------------------
    op.execute("""
        ALTER TABLE leave_logs
        ADD COLUMN IF NOT EXISTS start_date DATE
        """)

    op.execute("""
        ALTER TABLE leave_logs
        ADD COLUMN IF NOT EXISTS end_date DATE
        """)

    op.execute("""
        ALTER TABLE leave_logs
        ADD COLUMN IF NOT EXISTS total_days NUMERIC(4,1)
        """)

    # Existing leave rows were deleted above, so these can safely
    # become NOT NULL.
    op.execute("""
        ALTER TABLE leave_logs
        ALTER COLUMN start_date SET NOT NULL
        """)

    op.execute("""
        ALTER TABLE leave_logs
        ALTER COLUMN end_date SET NOT NULL
        """)

    op.execute("""
        ALTER TABLE leave_logs
        ALTER COLUMN total_days SET NOT NULL
        """)

    # ---------------------------------------------------------
    # 9. Parent-level date constraint
    # ---------------------------------------------------------
    op.create_check_constraint(
        "chk_leave_logs_valid_date_range",
        "leave_logs",
        "start_date <= end_date",
    )

    # ---------------------------------------------------------
    # 10. Parent-level indexes
    # ---------------------------------------------------------
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_leave_logs_user_range
        ON leave_logs (user_id, start_date, end_date)
        """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_leave_logs_org_range
        ON leave_logs (organization_id, start_date, end_date)
        """)

    # ---------------------------------------------------------
    # 11. Create new PostgreSQL enum types
    # ---------------------------------------------------------
    leave_portion_enum = postgresql.ENUM(
        "full",
        "half",
        name="leave_portion",
    )

    half_slot_enum = postgresql.ENUM(
        "first",
        "second",
        name="half_slot",
    )

    leave_portion_enum.create(
        op.get_bind(),
        checkfirst=True,
    )

    half_slot_enum.create(
        op.get_bind(),
        checkfirst=True,
    )

    # ---------------------------------------------------------
    # 12. Remove leave_log_days if somehow already present
    #
    # This makes the migration recoverable in your current
    # development database.
    # ---------------------------------------------------------
    op.execute("DROP TABLE IF EXISTS leave_log_days")

    # ---------------------------------------------------------
    # 13. Create leave_log_days
    # ---------------------------------------------------------
    op.create_table(
        "leave_log_days",
        # -----------------------------------------------------
        # Primary key
        # -----------------------------------------------------
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        # -----------------------------------------------------
        # Parent leave request
        # -----------------------------------------------------
        sa.Column(
            "leave_log_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        # -----------------------------------------------------
        # Denormalized user/organization references
        # -----------------------------------------------------
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        # -----------------------------------------------------
        # Actual leave date
        # -----------------------------------------------------
        sa.Column(
            "leave_date",
            sa.Date(),
            nullable=False,
        ),
        # -----------------------------------------------------
        # Full or half day
        # -----------------------------------------------------
        sa.Column(
            "portion",
            postgresql.ENUM(
                "full",
                "half",
                name="leave_portion",
                create_type=False,
            ),
            nullable=False,
        ),
        # -----------------------------------------------------
        # First or second half
        #
        # NULL for full-day leave.
        # -----------------------------------------------------
        sa.Column(
            "half_slot",
            postgresql.ENUM(
                "first",
                "second",
                name="half_slot",
                create_type=False,
            ),
            nullable=True,
        ),
        # -----------------------------------------------------
        # Occupied slot
        #
        # full  = [0,2)
        # first = [0,1)
        # second = [1,2)
        # -----------------------------------------------------
        sa.Column(
            "slot",
            postgresql.INT4RANGE(),
            nullable=False,
        ),
        # -----------------------------------------------------
        # Timestamps
        # -----------------------------------------------------
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
        # -----------------------------------------------------
        # Soft delete
        # -----------------------------------------------------
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "deleted_by",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        # -----------------------------------------------------
        # Foreign keys
        # -----------------------------------------------------
        sa.ForeignKeyConstraint(
            ["leave_log_id"],
            ["leave_logs.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
        ),
        sa.ForeignKeyConstraint(
            ["deleted_by"],
            ["users.id"],
        ),
        # -----------------------------------------------------
        # Primary key
        # -----------------------------------------------------
        sa.PrimaryKeyConstraint(
            "id",
        ),
        # -----------------------------------------------------
        # One day can occur only once in one leave request.
        # -----------------------------------------------------
        sa.UniqueConstraint(
            "leave_log_id",
            "leave_date",
            name="uq_leave_log_days_leave_log_date",
        ),
        # -----------------------------------------------------
        # Full day:
        #   half_slot must be NULL
        #
        # Half day:
        #   half_slot must be first or second
        # -----------------------------------------------------
        sa.CheckConstraint(
            """
            (
                portion = 'full'
                AND half_slot IS NULL
            )
            OR
            (
                portion = 'half'
                AND half_slot IS NOT NULL
            )
            """,
            name="chk_leave_log_days_portion_half_slot",
        ),
        # -----------------------------------------------------
        # Prevent overlapping active leave.
        #
        # Same user + same date + overlapping slot = conflict.
        #
        # full  = [0,2)
        # first = [0,1)
        # second = [1,2)
        #
        # Therefore:
        # first + second -> allowed
        # first + first -> conflict
        # second + second -> conflict
        # full + either -> conflict
        # -----------------------------------------------------
        postgresql.ExcludeConstraint(
            ("user_id", "="),
            ("leave_date", "="),
            ("slot", "&&"),
            where=sa.text("deleted_at IS NULL"),
            name="excl_leave_log_days_active_overlap",
            using="gist",
        ),
    )

    # ---------------------------------------------------------
    # 14. Child-table indexes
    # ---------------------------------------------------------
    op.create_index(
        "idx_leave_log_days_user_date",
        "leave_log_days",
        ["user_id", "leave_date"],
    )

    op.create_index(
        "idx_leave_log_days_org_date",
        "leave_log_days",
        ["organization_id", "leave_date"],
    )

    op.create_index(
        "idx_leave_log_days_leave_log",
        "leave_log_days",
        ["leave_log_id"],
    )


def downgrade() -> None:
    # ---------------------------------------------------------
    # This downgrade is intentionally destructive.
    #
    # The upgrade deletes the old leave data, so it cannot be
    # reconstructed.
    # ---------------------------------------------------------

    # ---------------------------------------------------------
    # 1. Remove child data
    # ---------------------------------------------------------
    op.execute("DELETE FROM leave_log_days")

    # ---------------------------------------------------------
    # 2. Remove parent data
    # ---------------------------------------------------------
    op.execute("DELETE FROM leave_logs")

    # ---------------------------------------------------------
    # 3. Drop child indexes
    # ---------------------------------------------------------
    op.execute("DROP INDEX IF EXISTS idx_leave_log_days_leave_log")

    op.execute("DROP INDEX IF EXISTS idx_leave_log_days_org_date")

    op.execute("DROP INDEX IF EXISTS idx_leave_log_days_user_date")

    # ---------------------------------------------------------
    # 4. Drop child table
    # ---------------------------------------------------------
    op.execute("DROP TABLE IF EXISTS leave_log_days")

    # ---------------------------------------------------------
    # 5. Drop parent indexes
    # ---------------------------------------------------------
    op.execute("DROP INDEX IF EXISTS idx_leave_logs_org_range")

    op.execute("DROP INDEX IF EXISTS idx_leave_logs_user_range")

    # ---------------------------------------------------------
    # 6. Drop parent constraint
    # ---------------------------------------------------------
    op.execute("""
        ALTER TABLE leave_logs
        DROP CONSTRAINT IF EXISTS chk_leave_logs_valid_date_range
        """)

    # ---------------------------------------------------------
    # 7. Remove total_days
    #
    # start_date/end_date are intentionally retained because
    # they already existed in the database before this revision.
    # ---------------------------------------------------------
    op.execute("""
        ALTER TABLE leave_logs
        DROP COLUMN IF EXISTS total_days
        """)

    # ---------------------------------------------------------
    # 8. Recreate old enum types
    # ---------------------------------------------------------
    leave_duration_enum = postgresql.ENUM(
        "full_day",
        "half_day",
        name="leave_duration",
    )

    half_day_period_enum = postgresql.ENUM(
        "first_half",
        "second_half",
        name="half_day_period",
    )

    leave_duration_enum.create(
        op.get_bind(),
        checkfirst=True,
    )

    half_day_period_enum.create(
        op.get_bind(),
        checkfirst=True,
    )

    # ---------------------------------------------------------
    # 9. Restore old single-table leave fields
    # ---------------------------------------------------------
    op.execute("""
        ALTER TABLE leave_logs
        ADD COLUMN IF NOT EXISTS leave_date DATE
        """)

    op.execute("""
        ALTER TABLE leave_logs
        ADD COLUMN IF NOT EXISTS leave_duration
        leave_duration
        """)

    # The previous statement above is intentionally not used
    # because PostgreSQL cannot infer the custom enum type from
    # the enum name in this form.
    #
    # Drop it if an incomplete column was somehow created.
    op.execute("""
        ALTER TABLE leave_logs
        DROP COLUMN IF EXISTS leave_duration
        """)

    op.add_column(
        "leave_logs",
        sa.Column(
            "leave_duration",
            postgresql.ENUM(
                "full_day",
                "half_day",
                name="leave_duration",
                create_type=False,
            ),
            nullable=True,
        ),
    )

    op.add_column(
        "leave_logs",
        sa.Column(
            "half_day_period",
            postgresql.ENUM(
                "first_half",
                "second_half",
                name="half_day_period",
                create_type=False,
            ),
            nullable=True,
        ),
    )

    # ---------------------------------------------------------
    # 10. Restore old constraint
    # ---------------------------------------------------------
    op.create_check_constraint(
        "chk_leave_logs_duration_period",
        "leave_logs",
        """
        (
            leave_duration = 'full_day'
            AND half_day_period IS NULL
        )
        OR
        (
            leave_duration = 'half_day'
            AND half_day_period IS NOT NULL
        )
        """,
    )

    # ---------------------------------------------------------
    # 11. Restore old indexes
    # ---------------------------------------------------------
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_leave_logs_user_date
        ON leave_logs (user_id, leave_date)
        """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_leave_logs_org_date
        ON leave_logs (organization_id, leave_date)
        """)

    # ---------------------------------------------------------
    # 12. Remove new enum types
    # ---------------------------------------------------------
    op.execute("DROP TYPE IF EXISTS leave_portion")

    op.execute("DROP TYPE IF EXISTS half_slot")
