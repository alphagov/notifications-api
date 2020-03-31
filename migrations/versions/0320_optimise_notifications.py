"""

Revision ID: 0320_optimise_notifications
Revises: 0319_contact_list_archived
Create Date: 2020-03-26 11:16:12.389524

"""
import os

from alembic import op

revision = '0320_optimise_notifications'
down_revision = '0319_contact_list_archived'
environment = os.environ['NOTIFY_ENVIRONMENT']


def upgrade():
    # We like to run this operation on live via the command prompt, to watch the progress and stop if necessary
    if environment not in ["live", "production"]:
        # Drop indexes notifications - no need to recreate these indexes
        op.execute('DROP INDEX IF EXISTS ix_notifications_key_type')
        op.execute('DROP INDEX IF EXISTS ix_notifications_api_key_id')
        op.execute('DROP INDEX IF EXISTS ix_notifications_notification_status')
        op.execute('DROP INDEX IF EXISTS ix_notifications_notification_type')
        op.execute('DROP INDEX IF EXISTS ix_notifications_service_id')

        # Create new composite indexes
        # PLEASE NOTE: that if you create index on production you need to add concurrently to the create statement,
        # however we are unable to do that inside a transaction like this upgrade method
        ix_notifications_service_id_composite = """
        CREATE INDEX ix_notifications_service_id_composite 
            on notifications (service_id, notification_type, notification_status, created_at)
        """
        op.execute(ix_notifications_service_id_composite)

        ix_notifications_notification_type_composite = """
            CREATE INDEX ix_notifications_notification_type_composite 
            on notifications (notification_type, notification_status, created_at)
        """
        op.execute(ix_notifications_notification_type_composite)
        # DROP and CREATE all other indexes
        op.execute('DROP INDEX IF EXISTS ix_notifications_client_reference')
        op.execute('CREATE INDEX ix_notifications_client_reference ON notifications (client_reference)')

        op.execute('DROP INDEX IF EXISTS ix_notifications_created_at')
        op.execute('CREATE INDEX ix_notifications_created_at ON notifications (created_at)')

        op.execute('DROP INDEX IF EXISTS ix_notifications_job_id')
        op.execute('CREATE INDEX ix_notifications_job_id ON notifications (job_id)')

        op.execute('DROP INDEX IF EXISTS ix_notifications_reference')
        op.execute('CREATE INDEX ix_notifications_reference ON notifications (reference)')

        op.execute('DROP INDEX IF EXISTS ix_notifications_service_created_at')
        op.execute(
            'CREATE INDEX ix_notifications_service_created_at ON notifications (service_id, created_at)')

        op.execute('DROP INDEX IF EXISTS ix_notifications_template_id')
        op.execute('CREATE INDEX ix_notifications_template_id ON notifications (template_id)')

        # Drop indexes notification_history
        op.execute('DROP INDEX IF EXISTS ix_notification_history_key_type')
        op.execute('DROP INDEX IF EXISTS ix_notification_history_api_key_id')
        op.execute('DROP INDEX IF EXISTS ix_notification_history_notification_status')
        op.execute('DROP INDEX IF EXISTS ix_notification_history_notification_type')
        op.execute('DROP INDEX IF EXISTS ix_notification_history_service_id')
        op.execute('DROP INDEX IF EXISTS ix_notification_history_week_created')


def downgrade():
    pass
