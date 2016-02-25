"""empty message

Revision ID: 0025_add_processing_dates
Revises: 0024_uix_user_to_service
Create Date: 2016-02-24 17:15:47.457200

"""

# revision identifiers, used by Alembic.
revision = '0025_add_processing_dates'
down_revision = '0024_uix_user_to_service'

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
