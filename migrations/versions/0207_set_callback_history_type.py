"""

Revision ID: 0207_set_callback_history_type
Revises: 0206_assign_callback_type
Create Date: 2018-07-18 10:43:43.864835

"""
from alembic import op
import sqlalchemy as sa


revision = '0207_set_callback_history_type'
down_revision = '0206_assign_callback_type'


def upgrade():
    op.execute("update service_callback_api_history set callback_type = 'delivery_status' where callback_type is null")


def downgrade():
    pass
