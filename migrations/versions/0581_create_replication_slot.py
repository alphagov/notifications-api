"""
Create Date: 2026-08-17 00:00:00
"""

from alembic import op
from sqlalchemy import text

revision = "0581_create_replication_slot"
down_revision = "0580_inbsmshst_srv_id_null_valid"
slot_name = "notify_wal2json_slot"

def upgrade():
    op.execute(
        text(
            f"""
            SELECT pg_create_logical_replication_slot('{slot_name}', 'wal2json')
            WHERE NOT EXISTS (
                SELECT 1
                FROM pg_replication_slots
                WHERE slot_name = '{slot_name}'
            )
            """
        )
    )


def downgrade():
    op.execute(
        text(
            f"""
            SELECT pg_drop_replication_slot('{slot_name}')
            WHERE EXISTS (
                SELECT 1
                FROM pg_replication_slots
                WHERE slot_name = '{slot_name}'
            )
            """
        )
    )
