"""

Revision ID: 0216_remove_colours
Revises: 0215_email_brand_type
Create Date: 2018-08-24 13:36:49.346156

"""
from alembic import op
import sqlalchemy as sa


revision = '0216_remove_colours'
down_revision = '0215_email_brand_type'


def upgrade():
    op.drop_column('email_branding', 'single_id_colour')
    op.drop_column('email_branding', 'banner_colour')


def downgrade():
    op.add_column('email_branding', sa.Column('banner_colour', sa.VARCHAR(length=7), autoincrement=False, nullable=True))
    op.add_column('email_branding', sa.Column('single_id_colour', sa.VARCHAR(length=7), autoincrement=False, nullable=True))
