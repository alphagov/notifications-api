"""
Create Date: 2026-07-01T16:39:58
"""

from alembic import op
from sqlalchemy import text

revision = "0554_create_replacation_slot"
down_revision = "0553_add_reason_to_provider"
slot_name = "notify_dashboard_replication_slot"

def upgrade():
    bind = op.get_bind()
    with op.get_context().autocommit_block():
        bind.execute(
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
    bind = op.get_bind()
    with op.get_context().autocommit_block():
        bind.execute(
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
