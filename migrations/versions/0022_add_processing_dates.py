"""empty message

Revision ID: 0022_add_processing_dates
Revises: 0021_add_job_metadata
Create Date: 2016-02-24 17:15:47.457200

"""

# revision identifiers, used by Alembic.
revision = '0022_add_processing_dates'
down_revision = '0022_add_invite_users'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('jobs', sa.Column('processing_finished', sa.DateTime(), nullable=True))
    op.add_column('jobs', sa.Column('processing_started', sa.DateTime(), nullable=True))
    op.add_column('notifications', sa.Column('sent_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('notifications', 'sent_at')
    op.drop_column('jobs', 'processing_started')
    op.drop_column('jobs', 'processing_finished')
