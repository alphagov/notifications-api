"""

Revision ID: 0177_add_virus_scan_statuses
Revises: 0176_alter_billing_columns
Create Date: 2018-02-21 14:05:04.448977

"""
from alembic import op


revision = '0177_add_virus_scan_statuses'
down_revision = '0176_alter_billing_columns'


def upgrade():
    op.execute("INSERT INTO notification_status_types (name) VALUES ('pending-virus-check')")
    op.execute("INSERT INTO notification_status_types (name) VALUES ('virus-scan-failed')")


def downgrade():
    op.execute("UPDATE notifications SET notification_status = 'created' WHERE notification_status = 'pending-virus-check'")
    op.execute("UPDATE notification_history SET notification_status = 'created' WHERE notification_status = 'pending-virus-check'")

    op.execute("UPDATE notifications SET notification_status = 'permanent-failure' WHERE notification_status = 'virus-scan-failed'")
    op.execute("UPDATE notification_history SET notification_status = 'permanent-failure' WHERE notification_status = 'virus-scan-failed'")

    op.execute("DELETE FROM notification_status_types WHERE name in ('pending-virus-check', 'virus-scan-failed')")
