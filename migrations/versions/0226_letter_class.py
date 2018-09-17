"""

Revision ID: 0226_letter_class
Revises: 0225_another_letter_org
Create Date: 2018-09-13 16:23:59.168877

"""
from alembic import op
import sqlalchemy as sa


revision = '0226_letter_class'
down_revision = '0225_another_letter_org'


def upgrade():
    op.add_column('services', sa.Column('letter_class', sa.String(length=255), nullable=True))
    op.add_column('services_history', sa.Column('letter_class', sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column('services_history', 'letter_class')
    op.drop_column('services', 'letter_class')
