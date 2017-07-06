"""empty message

Revision ID: 0106_noti_status_null
Revises: 0105_opg_letter_org
Create Date: 2017-07-03 16:58:38.650154

"""

# revision identifiers, used by Alembic.
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0106_noti_status_null'
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
