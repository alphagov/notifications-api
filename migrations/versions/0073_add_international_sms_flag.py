"""empty message

Revision ID: 0073_add_international_sms_flag
Revises: 0072_add_dvla_orgs
Create Date: 2017-10-25 17:37:27.660723

"""

# revision identifiers, used by Alembic.
revision = '0073_add_international_sms_flag'
down_revision = '0072_add_dvla_orgs'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('services', sa.Column('can_send_international_sms', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('services_history', sa.Column('can_send_international_sms', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column('services_history', 'can_send_international_sms')
    op.drop_column('services', 'can_send_international_sms')
