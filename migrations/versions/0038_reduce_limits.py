"""empty message

Revision ID: 0038_reduce_limits
Revises: 0037_more_job_states
Create Date: 2016-03-08 11:16:25.659463

"""

# revision identifiers, used by Alembic.
revision = '0038_reduce_limits'
down_revision = '0037_more_job_states'

from alembic import op


def upgrade():
    op.execute('update services set "limit" = 50')


def downgrade():
    pass