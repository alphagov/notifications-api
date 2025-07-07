"""
Create Date: 2025-07-07 08:26:08.720911
"""

from alembic import op

revision = '0507_n_history_service_id_index'
down_revision = '0506_n_history_job_id_index'


def upgrade():
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_notification_history_service_id on notification_history (service_id)"
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS ix_notification_history_service_id"
        )
