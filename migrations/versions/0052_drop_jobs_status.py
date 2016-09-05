"""empty message

Revision ID: 0052_drop_jobs_status
Revises: 0051_set_job_status
Create Date: 2016-08-25 15:56:31.779399

"""

# revision identifiers, used by Alembic.
revision = '0052_drop_jobs_status'
down_revision = '0051_set_job_status'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade():
    op.alter_column('jobs', 'job_status', existing_type=sa.VARCHAR(length=255), nullable=False)
    op.alter_column('jobs', 'status', existing_type=sa.VARCHAR(length=255), nullable=True)


def downgrade():
    # this downgrade leaves status empty and with no not null constraint.
    op.alter_column('jobs', 'status', existing_type=sa.VARCHAR(length=255), nullable=False)
    op.alter_column('jobs', 'job_status', existing_type=sa.VARCHAR(length=255), nullable=True)
