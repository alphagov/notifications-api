"""

Revision ID: 0109_rem_old_noti_status
Revises: 0108_change_logo_not_nullable
Create Date: 2017-07-10 14:25:15.712055

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0109_rem_old_noti_status'
down_revision = '0108_change_logo_not_nullable'


def upgrade():
    op.drop_column('notification_history', 'status')
    op.drop_column('notifications', 'status')


def downgrade():
    op.add_column(
        'notifications',
        sa.Column(
            'status',
            postgresql.ENUM(
                'created', 'sending', 'delivered', 'pending', 'failed', 'technical-failure',
                'temporary-failure', 'permanent-failure', 'sent', name='notify_status_type'
            ),
            autoincrement=False,
            nullable=True
        )
    )
    op.add_column(
        'notification_history',
        sa.Column(
            'status',
            postgresql.ENUM(
                'created', 'sending', 'delivered', 'pending', 'failed', 'technical-failure',
                'temporary-failure', 'permanent-failure', 'sent', name='notify_status_type'
            ),
            autoincrement=False,
            nullable=True
        )
    )
