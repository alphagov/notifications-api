"""

Revision ID: 0086_add_norm_to_notification
Revises: 0085_update_incoming_to_inbound
Create Date: 2017-05-23 10:37:00.404087

"""

from alembic import op
import sqlalchemy as sa

revision = '0086_add_norm_to_notification'
down_revision = '0085_update_incoming_to_inbound'


def upgrade():
    op.add_column('notifications', sa.Column('normalised_to', sa.String(), nullable=True))


def downgrade():
    op.drop_column('notifications', 'normalised_to')
