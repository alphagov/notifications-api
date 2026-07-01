"""
Create Date: 2026-07-01T16:39:58
"""

from alembic import op

revision = "0553_create_replacation_slot"
down_revision = "0552_update_letter_pricing"


def upgrade():
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_replication_slots
                WHERE slot_name = 'notify_dashboard_replication_slot'
            ) THEN
                PERFORM 1
                FROM pg_create_logical_replication_slot('notify_dashboard_replication_slot', 'wal2json');
            END IF;
        END
        $$;
        """
    )


def downgrade():
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_replication_slots
                WHERE slot_name = 'notify_dashboard_replication_slot'
            ) THEN
                PERFORM pg_drop_replication_slot('notify_dashboard_replication_slot');
            END IF;
        END
        $$;
        """
    )
