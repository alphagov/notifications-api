"""
Create Date: 2024-06-01 16:34:30.12345
"""

from alembic import op


revision = "0452_th_has_unsub_link_backfill"
down_revision = "0451_t_has_unsub_link_not_null"


def upgrade():
    op.execute("UPDATE templates_history SET has_unsubscribe_link=false WHERE has_unsubscribe_link IS NULL")


def downgrade():
    # non-reversible
    pass
