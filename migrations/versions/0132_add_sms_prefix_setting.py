"""

Revision ID: 0132_add_sms_prefix_setting
Revises: 0131_user_auth_types
Create Date: 2017-11-03 11:07:40.537006

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0132_add_sms_prefix_setting'
down_revision = '0131_user_auth_types'


def upgrade():
    op.add_column('services', sa.Column('prefix_sms', sa.Boolean(), nullable=True))
    op.add_column('services_history', sa.Column('prefix_sms', sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column('services_history', 'prefix_sms')
    op.drop_column('services', 'prefix_sms')
