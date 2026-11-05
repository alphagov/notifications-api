"""
Create Date: 2026-11-05 16:00:00
"""

from alembic import op

revision = "0584_create_index_notif_history"
down_revision = "0583_add_filename_column"


def upgrade():
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "
            "ix_notif_history_id_status "
            "ON notification_history (id, notification_status);"
        )

def downgrade():
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_notif_history_id_status;")
