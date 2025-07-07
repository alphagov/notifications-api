"""
Create Date: 2025-07-04 09:28:38.029592
"""

from alembic import op

revision = '0506_n_history_job_id_index'
down_revision = '0505_n_history_api_key_index'

# NOTE: This migration was a no-op, since the index already existed

def upgrade():
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_notification_history_job_id on notification_history (job_id)"
        )


def downgrade():
    pass
