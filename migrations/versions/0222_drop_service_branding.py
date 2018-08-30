"""
 Revision ID: 0222_drop_service_branding
Revises: 0221_nullable_service_branding
Create Date: 2018-08-24 13:36:49.346156
 """
from alembic import op
import sqlalchemy as sa


revision = '0222_drop_service_branding'
down_revision = '0221_nullable_service_branding'


def upgrade():

    op.drop_column('services_history', 'branding')
    op.drop_column('services', 'branding')


def downgrade():

    op.add_column('services', sa.Column('branding', sa.String(length=255)))
    op.add_column('services_history', sa.Column('branding', sa.String(length=255)))
