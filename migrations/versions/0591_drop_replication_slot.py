"""
Create Date: 2026-11-20 00:00:00
"""

from alembic import op
from sqlalchemy import text

revision = "0591_drop_replication_slot"
down_revision = "0590_nh_sv_id_tpt_id_null_valid"
slot_name = "notify_wal2json_slot"


def upgrade():
    # uncomment this if you really desperately need the database state as it was between
    # migrations 0581 (where this slot was created) and 0591, otherwise leave it commented out
    # because it causes CI flakes due to replication slot names being cluster-global and
    # colliding with each other on instances running multiple databases. ultimately managing
    # replication slots through migrations is probably not the best way to do it anyway.
    #
    # op.execute(
    #     text(
    #         f"""
    #         SELECT pg_drop_replication_slot('{slot_name}')
    #         WHERE EXISTS (
    #             SELECT 1
    #             FROM pg_replication_slots
    #             WHERE slot_name = '{slot_name}'
    #         )
    #         """
    #     )
    # )
    pass

def downgrade():
    # as above
    #
    # op.execute(
    #     text(
    #         f"""
    #         SELECT pg_create_logical_replication_slot('{slot_name}', 'wal2json')
    #         WHERE NOT EXISTS (
    #             SELECT 1
    #             FROM pg_replication_slots
    #             WHERE slot_name = '{slot_name}'
    #         )
    #         """
    #     )
    # )
    pass
