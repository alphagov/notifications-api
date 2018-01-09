"""

Revision ID: 0157_add_rate_limit_to_service
Revises: 0156_set_temp_letter_contact
Create Date: 2018-01-08 16:13:25.733336

"""
from alembic import op
import sqlalchemy as sa


revision = '0157_add_rate_limit_to_service'
down_revision = '0156_set_temp_letter_contact'


def upgrade():
    op.add_column('services', sa.Column('rate_limit', sa.Integer(), nullable=False, server_default='3000'))
    op.add_column('services_history', sa.Column('rate_limit', sa.Integer(), nullable=False, server_default='3000'))


def downgrade():
    op.drop_column('services_history', 'rate_limit')
    op.drop_column('services', 'rate_limit')
