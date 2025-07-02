"""
Create Date: 2025-07-02 07:41:55.066737
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0505_n_history_api_key_index'
down_revision = '0504_remove_upload_letters'


def upgrade():
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_notification_history_api_key_id on notification_history (api_key_id)"
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS ix_notification_history_api_key_id"
        )
