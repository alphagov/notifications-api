"""
Create Date: 2026-07-20T00:00:00
"""

from alembic import op

revision = "0554_add_notif_status_constraint"
down_revision = "0553_add_reason_to_provider"


def upgrade():
    op.execute(
        "-- squawk-ignore require-timeout-settings\n"
        "ALTER TABLE notifications "
        "ADD CONSTRAINT ck_notifications_notification_status_not_null "
        "CHECK (notification_status IS NOT NULL) NOT VALID;"
    )


def downgrade():
    op.execute(
        "ALTER TABLE notifications DROP CONSTRAINT IF EXISTS ck_notifications_notification_status_not_null;"
    )
