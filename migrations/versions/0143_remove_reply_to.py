"""

Revision ID: 0143_remove_reply_to
Revises: 0142_validate_constraint
Create Date: 2017-11-20 14:35:16.826398

"""
from alembic import op
import sqlalchemy as sa


revision = '0143_remove_reply_to'
down_revision = '0142_validate_constraint'


def upgrade():
    op.drop_column('services', 'letter_contact_block')
    op.drop_column('services', 'reply_to_email_address')
    op.drop_column('services_history', 'letter_contact_block')
    op.drop_column('services_history', 'reply_to_email_address')


def downgrade():
    op.add_column('services_history', sa.Column('reply_to_email_address', sa.TEXT(), autoincrement=False, nullable=True))
    op.add_column('services_history', sa.Column('letter_contact_block', sa.TEXT(), autoincrement=False, nullable=True))
    op.add_column('services', sa.Column('reply_to_email_address', sa.TEXT(), autoincrement=False, nullable=True))
    op.add_column('services', sa.Column('letter_contact_block', sa.TEXT(), autoincrement=False, nullable=True))
