"""
Create Date: 2026-07-02T00:00:00
"""

from alembic import op

revision = "0554_notification_id_date_status"
down_revision = "0553_create_replacation_slot"


def upgrade():
    op.execute("SET lock_timeout = '1s';")
    op.execute("SET statement_timeout = '5s';")

    # We need a unique index on (id, notification_status) for REPLICA IDENTITY USING INDEX.
    # Build a validated check first so PostgreSQL can avoid a table scan when setting NOT NULL.
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TABLE notifications "
            "ADD CONSTRAINT ck_notifications_notification_status_not_null "
            "CHECK (notification_status IS NOT NULL) NOT VALID;"
        )
        op.execute(
            "ALTER TABLE notifications "
            "VALIDATE CONSTRAINT ck_notifications_notification_status_not_null;"
        )
        op.execute("ALTER TABLE notifications ALTER COLUMN notification_status SET NOT NULL;")

    with op.get_context().autocommit_block():
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "
            "ix_notifications_id_date_status "
            "ON notifications (id, created_at, notification_status);"
        )

def downgrade():
    op.execute("ALTER TABLE notifications ALTER COLUMN notification_status DROP NOT NULL;")
    op.execute("ALTER TABLE notifications DROP CONSTRAINT IF EXISTS ck_notifications_notification_status_not_null;")

    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS ix_notifications_id_date_status;"
        )
