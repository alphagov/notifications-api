"""empty message

Revision ID: 0082_add_created_to_job_stats
Revises: 0081_add_job_stats
Create Date: 2017-05-11 15:05:53.420946

"""

# revision identifiers, used by Alembic.
revision = '0082_add_created_to_job_stats'
down_revision = '0081_add_job_stats'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('job_statistics', sa.Column('created_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('job_statistics', 'created_at')
