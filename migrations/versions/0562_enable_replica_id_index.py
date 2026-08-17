"""
Create Date: 2026-08-17 00:00:00
"""

from alembic import op

revision = "0562_enable_replica_id_index"
down_revision = "0561_add_go_live_admin_template"


def upgrade():
    op.execute("ALTER TABLE notifications REPLICA IDENTITY USING INDEX ix_notifications_id_status;")

def downgrade():
    op.execute("ALTER TABLE notifications REPLICA IDENTITY DEFAULT;")
