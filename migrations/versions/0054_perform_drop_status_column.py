"""empty message

Revision ID: 0054_perform_drop_status_column
Revises: 0053_cancelled_job_status
Create Date: 2016-08-25 15:56:31.779399

"""

# revision identifiers, used by Alembic.
revision = '0054_perform_drop_status_column'
down_revision = '0053_cancelled_job_status'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade():
    op.drop_column('jobs', 'status')


def downgrade():
    op.add_column('jobs', sa.Column('status', postgresql.ENUM('pending', 'in progress', 'finished', 'sending limits exceeded', name='job_status_types'), autoincrement=False, nullable=True))
