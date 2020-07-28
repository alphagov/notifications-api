"""

Revision ID: 0327_idx_notification_history
Revises: 0326_broadcast_event
Create Date: 2020-07-28 08:11:07.666708

"""
import os
from alembic import op

revision = '0327_idx_notification_history'
down_revision = '0326_broadcast_event'

environment = os.environ['NOTIFY_ENVIRONMENT']


def upgrade():
    if environment not in ["live", "production"]:
        op.execute('DROP INDEX IF EXISTS ix_notifications_service_id_created_at')
        op.execute('DROP INDEX IF EXISTS ix_notification_history_created_at')
        op.execute('DROP INDEX IF EXISTS ix_notification_history_service_id_created_at')

        index = """
            CREATE INDEX IF NOT EXISTS ix_notification_history_service_id_composite 
            on notification_history(service_id, key_type, notification_type, created_at)
            """
        op.execute(index)

        composite_index = """
        CREATE INDEX IF NOT EXISTS ix_notifications_notification_type_composite 
            on notifications(notification_type, notification_status, created_at)
        """
        op.execute(composite_index)

        # need to run on PROD
        op.execute('DROP INDEX IF EXISTS ix_notification_history_service_id')
        op.execute('DROP INDEX IF EXISTS ix_notification_history_template_id')
        op.execute('DROP INDEX IF EXISTS ix_notification_history_notification_status')
        op.execute('DROP INDEX IF EXISTS ix_notification_history_notification_type')


def downgrade():
    if environment not in ["live", "production"]:
        op.execute("""
            CREATE INDEX IF NOT EXISTS ix_notifications_service_id_created_at 
            ON notifications(service_id, date(created_at))
            """)
        op.execute("""
            CREATE INDEX IF NOT EXISTS ix_notification_history_created_at 
            on notification_history(created_at)
            """)
        op.execute("""
            CREATE INDEX IF NOT EXISTS ix_notification_history_service_id_created_at 
            on notification_history(created_at)
            """)

        op.execute('DROP INDEX IF EXISTS ix_notification_history_service_id_composite')

        # need to run on PROD

        op.execute('DROP INDEX IF EXISTS ix_notifications_notification_type_composite')
        op.execute('CREATE INDEX IF NOT EXISTS ix_notification_history_service_id on notification_history (service_id)')
        op.execute("""
            CREATE INDEX IF NOT EXISTS ix_notification_history_template_id on notification_history (template_id)
            """)
        op.execute("""
            CREATE INDEX IF NOT EXISTS ix_notification_history_notification_status 
            on notification_history (notification_status)
            """)
        op.execute("""
            CREATE INDEX IF NOT EXISTS ix_notification_history_notification_type 
            on notification_history (notification_type)
            """)
