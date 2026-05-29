"""
Create Date: 2026-05-19T00:00:00
"""

from alembic import op

revision = "0553_notifications_id_status_idx"
down_revision = "0552_create_replacation_slot"


def upgrade():
    op.execute("ALTER TABLE notifications ALTER COLUMN notification_status SET NOT NULL;")

    with op.get_context().autocommit_block():
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
