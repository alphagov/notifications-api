"""
Create Date: 2024-06-01 16:35:30.12345
"""

from alembic import op
import sqlalchemy as sa


revision = "0449_t_has_unsub_link_constraint"
down_revision = "0448_t_has_unsub_link_backfill"


def upgrade():
    # acquires access exclusive, but only very briefly as the not_valid stops it doing a full table scan
    op.create_check_constraint(
        "ck_templates_has_unsubscribe_link_not_null_check",
        "templates",
        sa.column("has_unsubscribe_link").is_not(None),
        postgresql_not_valid=True,
    )


def downgrade():
    op.drop_constraint("ck_templates_has_unsubscribe_link_not_null_check", "templates")
