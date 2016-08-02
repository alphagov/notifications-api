"""empty message

Revision ID: 0043_notification_indexes
Revises: 0042_notification_history
Create Date: 2016-08-01 10:37:41.198070

"""

# revision identifiers, used by Alembic.
revision = '0043_notification_indexes'
down_revision = '0042_notification_history'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_index(op.f('ix_notifications_created_at'), 'notifications', ['created_at'])
    op.create_index(op.f('ix_notification_history_created_at'), 'notification_history', ['created_at'])

    op.create_index(op.f('ix_notifications_status'), 'notifications', ['status'])
    op.create_index(op.f('ix_notification_history_status'), 'notification_history', ['status'])

    op.create_index(op.f('ix_notifications_notification_type'), 'notifications', ['notification_type'])
    op.create_index(op.f('ix_notification_history_notification_type'), 'notification_history', ['notification_type'])

    op.create_index(
        'ix_notification_history_week_created',
        'notification_history',
        [sa.text("date_trunc('week', created_at)")]
    )


def downgrade():
    op.drop_index(op.f('ix_notifications_created_at'), table_name='notifications')
    op.drop_index(op.f('ix_notification_history_created_at'), table_name='notification_history')

    op.drop_index(op.f('ix_notifications_status'), table_name='notifications')
    op.drop_index(op.f('ix_notification_history_status'), table_name='notification_history')

    op.drop_index(op.f('ix_notifications_notification_type'), table_name='notifications')
    op.drop_index(op.f('ix_notification_history_notification_type'), table_name='notification_history')

    op.drop_index(op.f('ix_notification_history_week_created'), table_name='notification_history')
