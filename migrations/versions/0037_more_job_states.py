"""empty message

Revision ID: 0037_more_job_states
Revises: 0036_notification_stats
Create Date: 2016-03-08 11:16:25.659463

"""

# revision identifiers, used by Alembic.
revision = '0037_more_job_states'
down_revision = '0036_notification_stats'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.drop_column('jobs', 'status')
    op.execute('DROP TYPE job_status_types')
    job_status_types = sa.Enum('pending', 'in progress', 'finished', 'sending limits exceeded', name='job_status_types')
    job_status_types.create(op.get_bind())
    op.add_column('jobs', sa.Column('status', job_status_types, nullable=True))
    op.get_bind()
    op.execute("update jobs set status='finished'")
    op.alter_column('jobs', 'status', nullable=False)


def downgrade():
    op.drop_column('jobs', 'status')
    op.execute('DROP TYPE job_status_types')
