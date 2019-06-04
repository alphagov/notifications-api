"""

Revision ID: 0295_api_key_constraint
Revises: 0294_add_verify_reply_to
Create Date: 2019-06-04 13:49:50.685493

"""
from alembic import op
import sqlalchemy as sa

revision = '0295_api_key_constraint'
down_revision = '0294_add_verify_reply_to'


def upgrade():
    op.drop_constraint('uix_service_to_key_name', 'api_keys', type_='unique')
    op.create_index('uix_service_to_key_name', 'api_keys', ['service_id', 'name'], unique=True,
                    postgresql_where=sa.text('expiry_date IS NULL'))


def downgrade():
    op.drop_index('uix_service_to_key_name', table_name='api_keys')
    op.create_unique_constraint('uix_service_to_key_name', 'api_keys', ['service_id', 'name'])
