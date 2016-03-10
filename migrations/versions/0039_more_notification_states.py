"""empty message

Revision ID: 0039_more_notification_states
Revises: 0038_reduce_limits
Create Date: 2016-03-08 11:16:25.659463

"""

# revision identifiers, used by Alembic.
revision = '0039_more_notification_states'
down_revision = '0038_reduce_limits'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade():
    op.drop_column('notifications', 'status')
    op.execute('DROP TYPE notification_status_types')
    notification_status_types = sa.Enum('sent', 'delivered', 'failed', 'complaint', 'bounce', name='notification_status_types')
    notification_status_types.create(op.get_bind())
    op.add_column('notifications', sa.Column('status', notification_status_types, nullable=True))
    op.get_bind()
    op.execute("update notifications set status='delivered'")
    op.alter_column('notifications', 'status', nullable=False)


def downgrade():
    op.drop_column('notifications', 'status')
    op.execute('DROP TYPE notification_status_types')
