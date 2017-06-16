"""empty message

Revision ID: 0097_notnull_inbound_provider
Revises: 0096_update_job_stats
Create Date: 2017-06-02 16:50:11.698423

"""

# revision identifiers, used by Alembic.
revision = '0097_notnull_inbound_provider'
down_revision = '0096_update_job_stats'

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
