"""empty message

Revision ID: 0049_set_job_status
Revises: 0048_job_scheduled_time
Create Date: 2016-08-24 13:21:51.744526

"""

# revision identifiers, used by Alembic.
revision = '0049_set_job_status'
down_revision = '0048_job_scheduled_time'

from alembic import op


def upgrade():
    op.execute("update jobs set job_status = status where job_status is null")
    pass


def downgrade():
    pass
