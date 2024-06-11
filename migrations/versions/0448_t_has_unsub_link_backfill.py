"""
Create Date: 2024-06-01 16:34:30.12345
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0448_t_has_unsub_link_backfill"
down_revision = "0447_unsubscribe_requests"


def upgrade():
    op.execute("UPDATE templates SET has_unsubscribe_link=false WHERE has_unsubscribe_link IS NULL")


def downgrade():
    # non-reversible
    pass
