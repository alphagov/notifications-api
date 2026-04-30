"""
Create Date: 2026-04-30T11:57:42
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0550_notifications_nondeliv_idx"
down_revision = "0549_remove_send_files_via_ui"


def upgrade():
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_notifications_nondelivered_service_id_composite",
            "notifications",
            ["service_id", "notification_type", "created_at"],
            unique=False,
            postgresql_where=sa.text("notification_status != 'delivered'"),
            postgresql_concurrently=True,
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_notifications_nondelivered_service_id_composite",
            "notifications",
            postgresql_where=sa.text("notification_status != 'delivered'"),
            postgresql_concurrently=True,
        )
