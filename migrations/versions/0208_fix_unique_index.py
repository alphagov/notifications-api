"""

Revision ID: 0208_fix_unique_index
Revises: 0207_set_callback_history_type
Create Date: 2018-07-25 13:55:24.941794

"""
from alembic import op

revision = '84c3b6eb16b3'
down_revision = '0207_set_callback_history_type'


def upgrade():
    op.create_unique_constraint('uix_service_callback_type', 'service_callback_api', ['service_id', 'callback_type'])
    op.drop_index('ix_service_callback_api_service_id', table_name='service_callback_api')
    op.create_index(op.f('ix_service_callback_api_service_id'), 'service_callback_api', ['service_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_service_callback_api_service_id'), table_name='service_callback_api')
    op.create_index('ix_service_callback_api_service_id', 'service_callback_api', ['service_id'], unique=True)
    op.drop_constraint('uix_service_callback_type', 'service_callback_api', type_='unique')
