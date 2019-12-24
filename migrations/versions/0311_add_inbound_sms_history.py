"""

Revision ID: 0311_add_inbound_sms_history
Revises: 0310_returned_letters_table
Create Date: 2019-12-20 15:38:53.358509

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0311_add_inbound_sms_history'
down_revision = '0310_returned_letters_table'


def upgrade():
    op.create_table('inbound_sms_history',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('service_id', postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column('notify_number', sa.String(), nullable=False),
    sa.Column('provider_date', sa.DateTime(), nullable=True),
    sa.Column('provider_reference', sa.String(), nullable=True),
    sa.Column('provider', sa.String(), nullable=False),
    sa.ForeignKeyConstraint(['service_id'], ['services.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_inbound_sms_history_service_id'), 'inbound_sms_history', ['service_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_inbound_sms_history_service_id'), table_name='inbound_sms_history')
    op.drop_table('inbound_sms_history')
