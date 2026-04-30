"""
Create Date: 2026-04-30T12:08:58
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0551_drop_ntfcns_failed_idx"
down_revision = "0550_notifications_nondeliv_idx"


def upgrade():
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_notifications_failed_service_id_composite",
            table_name="notifications",
            postgresql_where=sa.text(
                "notification_status IN ('technical-failure', 'temporary-failure', 'permanent-failure', 'validation-failed', 'virus-scan-failed', 'returned-letter')"
            ),
            postgresql_concurrently=True,
        )


def downgrade():
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
