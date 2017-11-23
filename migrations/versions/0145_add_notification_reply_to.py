"""

Revision ID: 0145_add_notification_reply_to
Revises: 0144_template_service_letter
Create Date: 2017-11-22 14:23:48.806781

"""
from alembic import op
import sqlalchemy as sa


revision = '0145_add_notification_reply_to'
down_revision = '0144_template_service_letter'


def upgrade():
    op.add_column('notifications', sa.Column('reply_to_text', sa.String(), nullable=True))


def downgrade():
    op.drop_column('notifications', 'reply_to_text')
