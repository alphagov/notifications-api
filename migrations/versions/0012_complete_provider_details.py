"""empty message

Revision ID: 0012_complete_provider_details
Revises: 0011_ad_provider_details
Create Date: 2016-05-05 09:18:26.926275

"""

# revision identifiers, used by Alembic.
revision = '0012_complete_provider_details'
down_revision = '0011_ad_provider_details'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():

    op.alter_column('provider_rates', 'provider_id',
               existing_type=postgresql.UUID(),
               nullable=False)
    op.drop_column('provider_rates', 'provider')
    op.alter_column('provider_statistics', 'provider_id',
               existing_type=postgresql.UUID(),
               nullable=False)
    op.drop_column('provider_statistics', 'provider')


def downgrade():

    op.add_column('provider_statistics', sa.Column('provider', postgresql.ENUM('mmg', 'twilio', 'firetext', 'ses', name='providers'), autoincrement=False, nullable=False))
    op.alter_column('provider_statistics', 'provider_id',
               existing_type=postgresql.UUID(),
               nullable=True)
    op.add_column('provider_rates', sa.Column('provider', postgresql.ENUM('mmg', 'twilio', 'firetext', 'ses', name='providers'), autoincrement=False, nullable=False))
    op.alter_column('provider_rates', 'provider_id',
               existing_type=postgresql.UUID(),
               nullable=True)
