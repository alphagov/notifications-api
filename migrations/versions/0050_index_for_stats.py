"""empty message

Revision ID: 0050_index_for_stats
Revises: 0048_job_scheduled_time
Create Date: 2016-08-24 13:21:51.744526

"""

# revision identifiers, used by Alembic.
revision = '0050_index_for_stats'
down_revision = '0048_job_scheduled_time'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_index(
        'ix_notifications_service_id_created_at',
        'notifications',
        ['service_id', sa.text("date(created_at)")]
    )
    op.create_index(
        'ix_notification_history_service_id_created_at',
        'notification_history',
        ['service_id', sa.text("date(created_at)")]
    )

def downgrade():
    op.drop_index(op.f('ix_notifications_service_id_created_at'), table_name='notifications')
    op.drop_index(op.f('ix_notification_history_service_id_created_at'), table_name='notification_history')
