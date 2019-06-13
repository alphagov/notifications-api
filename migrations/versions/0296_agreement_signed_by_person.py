"""

Revision ID: 0296_agreement_signed_by_person
Revises: 0295_api_key_constraint
Create Date: 2019-06-13 16:40:32.982607

"""
from alembic import op
import sqlalchemy as sa

revision = '0296_agreement_signed_by_person'
down_revision = '0295_api_key_constraint'


def upgrade():
    op.add_column('organisation', sa.Column('agreement_signed_on_behalf_of_email_address', sa.String(length=255), nullable=True))
    op.add_column('organisation', sa.Column('agreement_signed_on_behalf_of_name', sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column('organisation', 'agreement_signed_on_behalf_of_name')
    op.drop_column('organisation', 'agreement_signed_on_behalf_of_email_address')
