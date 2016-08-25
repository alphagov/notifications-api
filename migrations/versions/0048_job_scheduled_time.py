"""empty message

Revision ID: 0048_job_scheduled_time
Revises: 0047_ukvi_spelling
Create Date: 2016-08-24 13:21:51.744526

"""

# revision identifiers, used by Alembic.
revision = '0048_job_scheduled_time'
down_revision = '0047_ukvi_spelling'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table('job_status',
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.PrimaryKeyConstraint('name')
    )
    op.add_column('jobs', sa.Column('job_status', sa.String(length=255), nullable=True))
    op.add_column('jobs', sa.Column('scheduled_for', sa.DateTime(), nullable=True))
    op.create_index(op.f('ix_jobs_job_status'), 'jobs', ['job_status'], unique=False)
    op.create_index(op.f('ix_jobs_scheduled_for'), 'jobs', ['scheduled_for'], unique=False)
    op.create_foreign_key(None, 'jobs', 'job_status', ['job_status'], ['name'])

    op.execute("insert into job_status values ('pending')")
    op.execute("insert into job_status values ('in progress')")
    op.execute("insert into job_status values ('finished')")
    op.execute("insert into job_status values ('sending limits exceeded')")
    op.execute("insert into job_status values ('scheduled')")


def downgrade():
    op.drop_constraint('jobs_job_status_fkey', 'jobs', type_='foreignkey')
    op.drop_index(op.f('ix_jobs_scheduled_for'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_job_status'), table_name='jobs')
    op.drop_column('jobs', 'scheduled_for')
    op.drop_column('jobs', 'job_status')
    op.drop_table('job_status')
