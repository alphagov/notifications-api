"""empty message

Revision ID: 0081_noti_status_as_enum
Revises: 0080_fix_rate_start_date
Create Date: 2017-05-02 14:50:04.070874

"""

# revision identifiers, used by Alembic.
revision = '0081_noti_status_as_enum'
down_revision = '0080_fix_rate_start_date'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table('notification_status',
        sa.Column('name', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('name')
    )

    op.execute('ALTER TABLE notifications ADD COLUMN notification_status text')
    op.execute('ALTER TABLE notification_history ADD COLUMN notification_status text')

    op.create_index(op.f('ix_notifications_notification_status'), 'notifications', ['notification_status'])
    op.create_index(op.f('ix_notification_history_notification_status'), 'notification_history', ['notification_status'])


def downgrade():
    op.execute('ALTER TABLE notifications DROP COLUMN notification_status')
    op.execute('ALTER TABLE notification_history DROP COLUMN notification_status')
    op.execute('DROP TABLE notification_status')
