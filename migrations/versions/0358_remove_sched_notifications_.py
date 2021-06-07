"""

Revision ID: 0358_remove_sched_notifications
Revises: 0357_validate_constraint
Create Date: 2021-06-07 09:09:06.376862

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0358_remove_sched_notifications'
down_revision = '0357_validate_constraint'


def upgrade():
    op.drop_index('ix_scheduled_notifications_notification_id', table_name='scheduled_notifications')
    op.drop_table('scheduled_notifications')


def downgrade():
    op.create_table('scheduled_notifications',
                    sa.Column('id', postgresql.UUID(), autoincrement=False, nullable=False),
                    sa.Column('notification_id', postgresql.UUID(), autoincrement=False, nullable=False),
                    sa.Column('scheduled_for', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
                    sa.Column('pending', sa.BOOLEAN(), autoincrement=False, nullable=False),
                    sa.ForeignKeyConstraint(['notification_id'], ['notifications.id'],
                                            name='scheduled_notifications_notification_id_fkey'),
                    sa.PrimaryKeyConstraint('id', name='scheduled_notifications_pkey')
                    )
    op.create_index('ix_scheduled_notifications_notification_id', 'scheduled_notifications', ['notification_id'],
                    unique=False)
