"""
Create Date: 2024-12-13 10:26:32.802054
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0483_rm_ntfcn_service_composite"
down_revision = "0482_ft_ntfcn_stat_tpt_date_idx"


def upgrade():
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_notifications_service_id_composite",
            table_name="notifications",
            if_exists=True,
            postgresql_concurrently=True,
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_notifications_service_id_composite",
            "notifications",
            ["service_id", "notification_type", "notification_status", "created_at"],
            if_not_exists=True,
            unique=False,
            postgresql_concurrently=True,
        )
