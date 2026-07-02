"""
Create Date: 2026-07-02T00:00:00
"""

from alembic import op

revision = "0555_enable_replica_id_index"
down_revision = "0554_notification_id_date_status"


def upgrade():
    op.execute("ALTER TABLE notifications REPLICA IDENTITY USING INDEX ix_notifications_id_date_status;")

def downgrade():
    op.execute("ALTER TABLE notifications REPLICA IDENTITY DEFAULT;")
