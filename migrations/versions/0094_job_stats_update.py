"""empty message

Revision ID: 0094_job_stats_update
Revises: 0093_data_gov_uk
Create Date: 2017-06-06 14:37:30.051647

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0094_job_stats_update'
down_revision = '0093_data_gov_uk'


def upgrade():
    op.add_column('job_statistics', sa.Column('sent', sa.BigInteger(), nullable=True))
    op.add_column('job_statistics', sa.Column('delivered', sa.BigInteger(), nullable=True))
    op.add_column('job_statistics', sa.Column('failed', sa.BigInteger(), nullable=True))


def downgrade():
    op.drop_column('job_statistics', 'sent')
    op.drop_column('job_statistics', 'failed')
    op.drop_column('job_statistics', 'delivered')
