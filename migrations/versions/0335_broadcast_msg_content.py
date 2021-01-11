"""

Revision ID: 0335_broadcast_msg_content
Revises: 0334_broadcast_message_number
Create Date: 2020-12-04 15:06:22.544803

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0335_broadcast_msg_content'
down_revision = '0334_broadcast_message_number'


def upgrade():
    op.add_column('broadcast_message', sa.Column('content', sa.Text(), nullable=True))
    op.alter_column('broadcast_message', 'template_id', nullable=True)
    op.alter_column('broadcast_message', 'template_version', nullable=True)


def downgrade():
    # downgrade fails if there are broadcasts without a template. This is deliberate cos I don't feel comfortable
    # deleting broadcasts.
    op.alter_column('broadcast_message', 'template_id', nullable=False)
    op.alter_column('broadcast_message', 'template_version', nullable=False)
    op.drop_column('broadcast_message', 'content')
