"""

Revision ID: 0213_brand_colour_domain
Revises: 0212_remove_caseworking
Create Date: 2018-08-16 16:29:41.374944

"""
from alembic import op
import sqlalchemy as sa

revision = '0213_brand_colour_domain'
down_revision = '0212_remove_caseworking'


def upgrade():
    op.add_column('email_branding', sa.Column('banner_colour', sa.String(length=7), nullable=True))
    op.add_column('email_branding', sa.Column('domain', sa.Text(), nullable=True))
    op.add_column('email_branding', sa.Column('single_id_colour', sa.String(length=7), nullable=True))


def downgrade():
    op.drop_column('email_branding', 'single_id_colour')
    op.drop_column('email_branding', 'domain')
    op.drop_column('email_branding', 'banner_colour')
