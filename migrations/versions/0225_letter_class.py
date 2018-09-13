"""

Revision ID: 0225_letter_class
Revises: 0224_returned_letter_status
Create Date: 2018-09-13 16:23:59.168877

"""
from alembic import op
import sqlalchemy as sa


revision = '0225_letter_class'
down_revision = '0224_returned_letter_status'


def upgrade():
    op.add_column('services', sa.Column('letter_class', sa.String(length=255), nullable=True))
    op.add_column('services_history', sa.Column('letter_class', sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column('services_history', 'letter_class')
    op.drop_column('services', 'letter_class')
