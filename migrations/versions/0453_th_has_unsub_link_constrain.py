"""
Create Date: 2024-06-01 16:35:30.12345
"""

from alembic import op
import sqlalchemy as sa


revision = "0453_th_has_unsub_link_constrain"
down_revision = "0452_th_has_unsub_link_backfill"


def upgrade():
    # acquires access exclusive, but only very briefly as the not_valid stops it doing a full table scan
    op.create_check_constraint(
        "ck_templates_history_has_unsubscribe_link_not_null_check",
        "templates_history",
        sa.column("has_unsubscribe_link").is_not(None),
        postgresql_not_valid=True,
    )


def downgrade():
    op.drop_constraint("ck_templates_history_has_unsubscribe_link_not_null_check", "templates_history")
