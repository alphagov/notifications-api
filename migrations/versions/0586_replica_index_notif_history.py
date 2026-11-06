"""
Create Date: 2026-11-05 16:00:00
"""

from alembic import op

revision = "0586_replica_index_notif_history"
down_revision = "0585_notif_history_status_null"


def upgrade():
    op.execute("ALTER TABLE notification_history REPLICA IDENTITY USING INDEX ix_notif_history_id_status;")

def downgrade():
    op.execute("ALTER TABLE notification_history REPLICA IDENTITY DEFAULT;")
