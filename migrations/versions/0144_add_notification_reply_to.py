"""

Revision ID: 0144_add_notification_reply_to
Revises: 0143_remove_reply_to
Create Date: 2017-11-22 14:23:48.806781

"""
from alembic import op
import sqlalchemy as sa


revision = '0144_add_notification_reply_to'
down_revision = '0143_remove_reply_to'


def upgrade():
    op.add_column('notifications', sa.Column('reply_to_text', sa.String(), nullable=True))


def downgrade():
    op.drop_column('notifications', 'reply_to_text')
