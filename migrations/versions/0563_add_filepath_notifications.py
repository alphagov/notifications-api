"""
Create Date: 2026-09-07 00:00:00
"""

from alembic import op

revision = "0563_add_filepath_notifications"
down_revision = "0562_enable_replica_id_index"


def upgrade():
    op.execute("ALTER TABLE notifications ADD COLUMN document_download_filepath jsonb")

def downgrade():
    op.execute("ALTER TABLE notifications DROP COLUMN document_download_filepath")
