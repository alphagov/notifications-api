"""empty message

Revision ID: 0076_add_intl_notification
Revises: 0075_create_rates_table
Create Date: 2017-04-25 11:34:43.229494

"""

# revision identifiers, used by Alembic.
revision = '0076_add_intl_notification'
down_revision = '0075_create_rates_table'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('notification_history', sa.Column('international', sa.Boolean(), nullable=True))
    op.add_column('notification_history', sa.Column('phone_prefix', sa.String(), nullable=True))
    op.add_column('notification_history', sa.Column('rate_multiplier', sa.Numeric(), nullable=True))
    op.add_column('notifications', sa.Column('international', sa.Boolean(), nullable=True))
    op.add_column('notifications', sa.Column('phone_prefix', sa.String(), nullable=True))
    op.add_column('notifications', sa.Column('rate_multiplier', sa.Numeric(), nullable=True))


def downgrade():
    op.drop_column('notifications', 'rate_multiplier')
    op.drop_column('notifications', 'phone_prefix')
    op.drop_column('notifications', 'international')
    op.drop_column('notification_history', 'rate_multiplier')
    op.drop_column('notification_history', 'phone_prefix')
    op.drop_column('notification_history', 'international')
