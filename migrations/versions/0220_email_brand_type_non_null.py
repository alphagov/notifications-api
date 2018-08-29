"""
 Revision ID: 0220_email_brand_type_non_null
Revises: 0219_default_email_branding
Create Date: 2018-08-24 13:36:49.346156
 """
from alembic import op

revision = '0220_email_brand_type_non_null'
down_revision = '0219_default_email_branding'


def upgrade():
    op.alter_column('email_branding', 'brand_type', nullable=False)


def downgrade():
    op.alter_column('email_branding', 'brand_type', nullable=True)
