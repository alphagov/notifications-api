"""
Create Date: 2026-11-05 16:00:00
"""

from alembic import op

revision = "0585_notif_history_status_null"
down_revision = "0584_create_index_notif_history"


def upgrade():
    op.execute(
        "-- squawk-ignore require-timeout-settings\n"
        "ALTER TABLE notification_history "
        "ADD CONSTRAINT ck_notification_history_status_not_null "
        "CHECK (notification_status IS NOT NULL) NOT VALID;"
    )
    op.execute(
        "ALTER TABLE notification_history "
        "VALIDATE CONSTRAINT ck_notification_history_status_not_null;"
    )
    op.execute("ALTER TABLE notification_history ALTER COLUMN notification_status SET NOT NULL;")


def downgrade():
    op.execute("ALTER TABLE notification_history ALTER COLUMN notification_status DROP NOT NULL;")
    op.execute(
        "ALTER TABLE notification_history DROP CONSTRAINT IF EXISTS ck_notification_history_status_not_null;"
    )