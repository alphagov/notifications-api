"""
Create Date: 2025-09-22 11:45:33.095877
"""

from alembic import op

revision = '0519_drop_n_hist_api_key_index'
down_revision = '0518_drop_n_hist_templates_index'


def upgrade():
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS ix_notification_history_api_key_id"
        )

def downgrade():
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_notification_history_api_key_id on notification_history (api_key_id)"
        )
