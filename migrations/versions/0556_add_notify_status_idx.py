"""
Create Date: 2026-07-20T00:00:00
"""

from alembic import op

revision = "0556_add_notify_status_idx"
down_revision = "0555_add_notify_status_not_null"


def upgrade():
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "
            "ix_notifications_id_status "
            "ON notifications (id, notification_status);"
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS ix_notifications_id_status;"
        )
