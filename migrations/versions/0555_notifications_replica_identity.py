"""
Set REPLICA IDENTITY on notifications table using (id, notification_status) index.

PostgreSQL requires all index columns to be NOT NULL for REPLICA IDENTITY USING INDEX,
and a unique index. This migration:
  1. Drops the existing non-unique index and recreates it as unique (required by PG).
  2. Sets REPLICA IDENTITY USING INDEX so only id + notification_status are written to WAL.

Revision ID: 0555_notif_replica_identity
Revises: 0554_create_service_stats
Create Date: 2026-05-19 00:00:00
"""

from alembic import op

revision = "0555_notif_replica_identity"
down_revision = "0554_create_service_stats"


def upgrade():
    ## NEEDED TO SET NOT NULL ON notification_status TO CREATE UNIQUE INDEX, THEN CAN SET REPLICA IDENTITY
    op.execute("ALTER TABLE notifications ALTER COLUMN notification_status SET NOT NULL;")

    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_notifications_id_notification_status",
            table_name="notifications",
            postgresql_concurrently=True,
        )
        op.create_index(
            "ix_notifications_id_notification_status",
            "notifications",
            ["id", "notification_status"],
            unique=True,
            postgresql_concurrently=True,
        )

    op.execute("ALTER TABLE notifications REPLICA IDENTITY USING INDEX ix_notifications_id_notification_status;")


def downgrade():
    op.execute("ALTER TABLE notifications REPLICA IDENTITY DEFAULT;")

    op.execute("ALTER TABLE notifications ALTER COLUMN notification_status DROP NOT NULL;")

    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_notifications_id_notification_status",
            table_name="notifications",
            postgresql_concurrently=True,
        )
        op.create_index(
            "ix_notifications_id_notification_status",
            "notifications",
            ["id", "notification_status"],
            unique=False,
            postgresql_concurrently=True,
        )


