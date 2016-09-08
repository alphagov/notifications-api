"""empty message

Revision ID: 0053_cancelled_job_status
Revises: 0052_drop_jobs_status
Create Date: 2016-09-01 14:34:06.839381

"""

# revision identifiers, used by Alembic.
revision = '0053_cancelled_job_status'
down_revision = '0052_drop_jobs_status'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.execute("INSERT INTO job_status VALUES ('cancelled')")

def downgrade():
    op.execute("UPDATE jobs SET job_status = 'finished' WHERE job_status = 'cancelled'")
    op.execute("DELETE FROM job_status WHERE name = 'cancelled';")
