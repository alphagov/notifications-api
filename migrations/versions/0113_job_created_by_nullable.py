"""empty message

Revision ID: 0113_job_created_by_nullable
Revises: 0112_add_start_end_dates
Create Date: 2017-07-27 11:12:34.938086

"""

# revision identifiers, used by Alembic.
revision = '0113_job_created_by_nullable'
down_revision = '0112_add_start_end_dates'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.alter_column('jobs', 'created_by_id', nullable=True)


def downgrade():
    # This will error if there are any jobs with no created_by - we'll have to decide how to handle those as and when
    # we downgrade
    op.alter_column('jobs', 'created_by_id', nullable=False)
