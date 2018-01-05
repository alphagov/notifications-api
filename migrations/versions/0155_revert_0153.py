"""

Revision ID: 0155_revert_0153
Revises: 0154_nullable_is_blank
Create Date: 2018-01-05 14:09:21.200102

"""
from alembic import op

revision = '0155_revert_0153'
down_revision = '0154_nullable_is_blank'


def upgrade():
    op.drop_column('templates', 'is_letter_contact_blank')
    op.drop_column('templates_history', 'is_letter_contact_blank')


def downgrade():
    pass
