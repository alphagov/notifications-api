"""
Create Date: 2026-08-17 00:00:00
"""

from alembic import op
from sqlalchemy import text

revision = "0562_create_replacation_slot"
down_revision = "0561_add_go_live_admin_template"
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
