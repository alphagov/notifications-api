"""
Create Date: 2026-05-19T00:00:00
"""

from alembic import op

revision = "0553_notifications_id_status_idx"
down_revision = "0552_create_replacation_slot"


def upgrade():
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_notifications_id_notification_status",
            "notifications",
            ["id", "notification_status"],
            unique=False,
            postgresql_concurrently=True,
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_notifications_id_notification_status",
            table_name="notifications",
            postgresql_concurrently=True,
        )
