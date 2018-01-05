"""

Revision ID: 0154_nullable_is_blank
Revises: 0153_add_is_letter_contact_blank
Create Date: 2018-01-05 15:49:36.522210

"""
from alembic import op
import sqlalchemy as sa


revision = '0154_nullable_is_blank'
down_revision = '0153_add_is_letter_contact_blank'


def upgrade():
    op.alter_column('templates', 'is_letter_contact_blank', nullable=True)
    op.alter_column('templates_history', 'is_letter_contact_blank', nullable=True)


def downgrade():
    op.alter_column('templates', 'is_letter_contact_blank', nullable=True)
    op.alter_column('templates_history', 'is_letter_contact_blank', nullable=True)
