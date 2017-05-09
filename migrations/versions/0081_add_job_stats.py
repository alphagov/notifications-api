"""empty message

Revision ID: 0081_add_job_stats
Revises: 0080_fix_rate_start_date
Create Date: 2017-05-09 11:21:06.959075

"""

# revision identifiers, used by Alembic.
revision = '0081_add_job_stats'
down_revision = '0080_fix_rate_start_date'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.create_table('job_statistics',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('job_id', postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column('emails_sent', sa.BigInteger(), nullable=False),
    sa.Column('emails_delivered', sa.BigInteger(), nullable=False),
    sa.Column('emails_failed', sa.BigInteger(), nullable=False),
    sa.Column('sms_sent', sa.BigInteger(), nullable=False),
    sa.Column('sms_delivered', sa.BigInteger(), nullable=False),
    sa.Column('sms_failed', sa.BigInteger(), nullable=False),
    sa.Column('letters_sent', sa.BigInteger(), nullable=False),
    sa.Column('letters_failed', sa.BigInteger(), nullable=False),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_job_statistics_job_id'), 'job_statistics', ['job_id'], unique=True)


def downgrade():
    op.drop_index(op.f('ix_job_statistics_job_id'), table_name='job_statistics')
    op.drop_table('job_statistics')
