"""
Create Date: 2025-07-07 11:03:04.356066
"""

from alembic import op

revision = '0508_n_history_templates_index'
down_revision = '0507_n_history_service_id_index'


def upgrade():
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_notification_history_template_composite on notification_history (template_id, template_version)"
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS ix_notification_history_template_composite"
        )
