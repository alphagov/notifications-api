"""
Create Date: 2024-12-02 21:30:07.663503
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0480_ntfcns_cpst_idx_nostatus"
down_revision = "0479_notifications_atv_union_all"


def upgrade():
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_notifications_service_id_ntype_created_at",
            "notifications",
            ["service_id", "notification_type", "created_at"],
            unique=False,
            postgresql_concurrently=True,
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.drop_index("ix_notifications_service_id_ntype_created_at", table_name="notifications")
