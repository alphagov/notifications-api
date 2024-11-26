"""
Create Date: 2024-11-15 14:01:27.039958
"""

from alembic import op
import sqlalchemy as sa

revision = "0476_notifications_failed_idx"
down_revision = "0475_ntfcn_hist_xstats_mcv"


def upgrade():
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_notifications_failed_service_id_composite",
            "notifications",
            ["service_id", "notification_type", "created_at"],
            unique=False,
            postgresql_where=sa.text(
                "notification_status IN ('technical-failure', 'temporary-failure', 'permanent-failure', 'validation-failed', 'virus-scan-failed', 'returned-letter')"
            ),
            postgresql_concurrently=True,
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_notifications_failed_service_id_composite",
            table_name="notifications",
            postgresql_where=sa.text(
                "notification_status IN ('technical-failure', 'temporary-failure', 'permanent-failure', 'validation-failed', 'virus-scan-failed', 'returned-letter')"
            ),
            postgresql_concurrently=True,
        )
