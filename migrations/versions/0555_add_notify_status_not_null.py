"""
Create Date: 2026-07-20T00:00:00
"""

from alembic import op

revision = "0555_add_notify_status_not_null"
down_revision = "0554_add_notif_status_constraint"


def upgrade():
    op.execute(
        "ALTER TABLE notifications "
        "VALIDATE CONSTRAINT ck_notifications_notification_status_not_null;"
    )
    op.execute("ALTER TABLE notifications ALTER COLUMN notification_status SET NOT NULL;")


def downgrade():
    op.execute("ALTER TABLE notifications ALTER COLUMN notification_status DROP NOT NULL;")
