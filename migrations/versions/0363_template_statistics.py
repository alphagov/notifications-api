"""

Revision ID: 0363_template_statistics
Revises: 0362_broadcast_msg_event
Create Date: 2022-01-21 16:19:58.158613

"""
import os

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0363_template_statistics'
down_revision = '0362_broadcast_msg_event'
environment = os.environ['NOTIFY_ENVIRONMENT']


def upgrade():
    if environment not in ["live", "production"]:
      conn = op.get_bind()
      conn.execute("""
          CREATE INDEX IF NOT EXISTS
          ix_notifications_template_statistics_for_service_by_day
          ON notifications
          (service_id, created_at, template_id, notification_status, notification_type, key_type)
      """)


def downgrade():
    if environment not in ["live", "production"]:
      conn = op.get_bind()
      conn.execute("""
          DROP INDEX ix_notifications_template_statistics_for_service_by_day
      """)
