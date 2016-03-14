"""empty message

Revision ID: 0040_add_reference
Revises: 0039_more_notification_states
Create Date: 2016-03-11 09:15:57.900192

"""

# revision identifiers, used by Alembic.
revision = '0040_add_reference'
down_revision = '0039_more_notification_states'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('notifications', sa.Column('reference', sa.String(), nullable=True))
    op.create_index(op.f('ix_notifications_reference'), 'notifications', ['reference'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_notifications_reference'), table_name='notifications')
    op.drop_column('notifications', 'reference')
