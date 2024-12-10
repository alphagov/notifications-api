"""
Create Date: 2024-12-10 13:12:35.576446
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0482_ft_ntfcn_stat_tpt_date_idx"
down_revision = "0481_receipt_service_live_req"


def upgrade():
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_ft_notification_status_template_id_bst_date",
            "ft_notification_status",
            ["template_id", "bst_date"],
            if_not_exists=True,
            unique=False,
            postgresql_concurrently=True,
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.drop_index("ix_ft_notification_status_template_id_bst_date", table_name="ft_notification_status")
