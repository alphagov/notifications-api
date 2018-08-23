"""

Revision ID: 0214_email_brand_type
Revises: 0213_brand_colour_domain
Create Date: 2018-08-23 11:48:00.800968

"""
from alembic import op
import sqlalchemy as sa

revision = '0214_email_brand_type'
down_revision = '0213_brand_colour_domain'


def upgrade():

    op.add_column('email_branding', sa.Column('brand_type', sa.String(length=255), nullable=True))
    op.create_index(op.f('ix_email_branding_brand_type'), 'email_branding', ['brand_type'], unique=False)
    op.create_foreign_key(None, 'email_branding', 'branding_type', ['brand_type'], ['name'])


def downgrade():
    op.drop_constraint("email_branding_brand_type_fkey", 'email_branding', type_='foreignkey')
    op.drop_index(op.f('ix_email_branding_brand_type'), table_name='email_branding')
    op.drop_column('email_branding', 'brand_type')
