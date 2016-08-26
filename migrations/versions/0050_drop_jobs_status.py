"""empty message

Revision ID: 0050_drop_jobs_status
Revises: 0049_set_job_status
Create Date: 2016-08-25 15:56:31.779399

"""

# revision identifiers, used by Alembic.
revision = '0050_drop_jobs_status'
down_revision = '0049_set_job_status'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.alter_column('jobs', 'job_status',
               existing_type=sa.VARCHAR(length=255),
               nullable=False)
    op.drop_column('jobs', 'status')


def downgrade():
    # this downgrade leaves status empty and with no not null constraint.
    op.add_column('jobs', sa.Column('status', postgresql.ENUM('pending', 'in progress', 'finished', 'sending limits exceeded', name='job_status_types'), autoincrement=False, nullable=True))
    op.alter_column('jobs', 'job_status',
               existing_type=sa.VARCHAR(length=255),
               nullable=True)
