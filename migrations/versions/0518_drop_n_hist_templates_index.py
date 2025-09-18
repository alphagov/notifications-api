"""
Create Date: 2025-09-18 09:19:47.763586
"""

from alembic import op

revision = '0518_drop_n_hist_templates_index'
down_revision = '0517_remove_broadcast_sequence'


def upgrade():
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS ix_notification_history_template_composite"
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_notification_history_template_composite on notification_history (template_id, template_version)"
        )
