"""

Revision ID: 0106_null_noti_status
Revises: 0105_opg_letter_org
Create Date: 2017-07-10 11:18:27.267721

"""

from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0106_null_noti_status'
down_revision = '0105_opg_letter_org'


def upgrade():
    op.alter_column(
        'notification_history',
        'status',
        existing_type=postgresql.ENUM(
            'created', 'sending', 'delivered', 'pending', 'failed', 'technical-failure',
            'temporary-failure', 'permanent-failure', 'sent', name='notify_status_type'
        ),
        nullable=True
    )
    op.alter_column(
        'notifications',
        'status',
        existing_type=postgresql.ENUM(
            'created', 'sending', 'delivered', 'pending', 'failed', 'technical-failure',
            'temporary-failure', 'permanent-failure', 'sent', name='notify_status_type'
        ),
        nullable=True
    )


def downgrade():
    op.alter_column(
        'notifications',
        'status',
        existing_type=postgresql.ENUM(
            'created', 'sending', 'delivered', 'pending', 'failed', 'technical-failure',
            'temporary-failure', 'permanent-failure', 'sent', name='notify_status_type'
        ),
        nullable=False
    )
    op.alter_column(
        'notification_history',
        'status',
        existing_type=postgresql.ENUM(
            'created', 'sending', 'delivered', 'pending', 'failed', 'technical-failure',
            'temporary-failure', 'permanent-failure', 'sent', name='notify_status_type'
        ),
        nullable=False
    )
