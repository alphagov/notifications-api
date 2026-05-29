"""
Create Date: 2026-05-14T16:39:58
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0552_create_replacation_slot"
down_revision = "0551_drop_ntfcns_failed_idx"


def upgrade():
    op.execute(
        "SELECT * FROM pg_create_logical_replication_slot('notify_dashboard_replication_slot', 'wal2json');"
    )


def downgrade():
    op.execute(
        "SELECT * FROM pg_drop_replication_slot('notify_dashboard_replication_slot');"
    )
