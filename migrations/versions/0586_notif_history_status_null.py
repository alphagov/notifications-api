"""
Create Date: 2026-11-05 16:00:00
"""

from alembic import op

revision = "0586_notif_history_status_null"
down_revision = "0585_notif_history_constraint"


def upgrade():
    op.execute(
        "ALTER TABLE notification_history "
        "VALIDATE CONSTRAINT ck_notification_history_status_not_null;"
    )
    op.execute("ALTER TABLE notification_history ALTER COLUMN notification_status SET NOT NULL;")


def downgrade():
    op.execute("ALTER TABLE notification_history ALTER COLUMN notification_status DROP NOT NULL;")
