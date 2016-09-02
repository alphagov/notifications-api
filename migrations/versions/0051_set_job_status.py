"""empty message

Revision ID: 0051_set_job_status
Revises: 0050_index_for_stats
Create Date: 2016-08-24 13:21:51.744526

"""

# revision identifiers, used by Alembic.
revision = '0051_set_job_status'
down_revision = '0050_index_for_stats'

from alembic import op


def upgrade():
    op.execute("update jobs set job_status = status where job_status is null")
    pass


def downgrade():
    pass
