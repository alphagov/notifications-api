"""empty message

Revision ID: 0094_notnull_inbound_provider
Revises: 0093_populate_inbound_provider
Create Date: 2017-06-02 16:50:11.698423

"""

# revision identifiers, used by Alembic.
revision = '0094_notnull_inbound_provider'
down_revision = '0093_populate_inbound_provider'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.alter_column('inbound_sms', 'provider',
               existing_type=sa.VARCHAR(),
               nullable=False)


def downgrade():
    op.alter_column('inbound_sms', 'provider',
               existing_type=sa.VARCHAR(),
               nullable=True)
