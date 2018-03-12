"""

Revision ID: 0175_drop_job_statistics_table
Revises: 0174_add_billing_facts
Create Date: 2018-03-12 10:27:09.050837

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0175_drop_job_statistics_table'
down_revision = '0174_add_billing_facts'


def upgrade():
    op.drop_table('job_statistics')


def downgrade():
    op.create_table('job_statistics',
    sa.Column('id', postgresql.UUID(), autoincrement=False, nullable=False),
    sa.Column('job_id', postgresql.UUID(), autoincrement=False, nullable=False),
    sa.Column('emails_sent', sa.BIGINT(), autoincrement=False, nullable=False),
    sa.Column('emails_delivered', sa.BIGINT(), autoincrement=False, nullable=False),
    sa.Column('emails_failed', sa.BIGINT(), autoincrement=False, nullable=False),
    sa.Column('sms_sent', sa.BIGINT(), autoincrement=False, nullable=False),
    sa.Column('sms_delivered', sa.BIGINT(), autoincrement=False, nullable=False),
    sa.Column('sms_failed', sa.BIGINT(), autoincrement=False, nullable=False),
    sa.Column('letters_sent', sa.BIGINT(), autoincrement=False, nullable=False),
    sa.Column('letters_failed', sa.BIGINT(), autoincrement=False, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.Column('updated_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.Column('sent', sa.BIGINT(), autoincrement=False, nullable=True),
    sa.Column('delivered', sa.BIGINT(), autoincrement=False, nullable=True),
    sa.Column('failed', sa.BIGINT(), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], name='job_statistics_job_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='job_statistics_pkey')
    )
