"""empty message

Revision ID: 0098_service_inbound_api
Revises: 0097_notnull_inbound_provider
Create Date: 2017-06-13 15:02:33.609656

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0098_service_inbound_api'
down_revision = '0097_notnull_inbound_provider'


def upgrade():
    op.create_table('service_inbound_api_history',
                    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
                    sa.Column('service_id', postgresql.UUID(as_uuid=True), nullable=False),
                    sa.Column('url', sa.String(length=255), nullable=False),
                    sa.Column('bearer_token', sa.String(length=255), nullable=False),
                    sa.Column('created_at', sa.DateTime(), nullable=False),
                    sa.Column('updated_at', sa.DateTime(), nullable=True),
                    sa.Column('updated_by_id', postgresql.UUID(as_uuid=True), nullable=False),
                    sa.Column('version', sa.Integer(), autoincrement=False, nullable=False),
                    sa.PrimaryKeyConstraint('id', 'version')
    )
    op.create_index(op.f('ix_service_inbound_api_history_service_id'), 'service_inbound_api_history', ['service_id'], unique=False)
    op.create_index(op.f('ix_service_inbound_api_history_updated_by_id'), 'service_inbound_api_history', ['updated_by_id'], unique=False)
    op.create_table('service_inbound_api',
                    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
                    sa.Column('service_id', postgresql.UUID(as_uuid=True), nullable=False),
                    sa.Column('url', sa.String(length=255), nullable=False),
                    sa.Column('bearer_token', sa.String(length=255), nullable=False),
                    sa.Column('created_at', sa.DateTime(), nullable=False),
                    sa.Column('updated_at', sa.DateTime(), nullable=True),
                    sa.Column('updated_by_id', postgresql.UUID(as_uuid=True), nullable=False),
                    sa.Column('version', sa.Integer(), nullable=False),
                    sa.ForeignKeyConstraint(['service_id'], ['services.id'], ),
                    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ),
                    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_service_inbound_api_service_id'), 'service_inbound_api', ['service_id'], unique=False)
    op.create_index(op.f('ix_service_inbound_api_updated_by_id'), 'service_inbound_api', ['updated_by_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_service_inbound_api_updated_by_id'), table_name='service_inbound_api')
    op.drop_index(op.f('ix_service_inbound_api_service_id'), table_name='service_inbound_api')
    op.drop_table('service_inbound_api')
    op.drop_index(op.f('ix_service_inbound_api_history_updated_by_id'), table_name='service_inbound_api_history')
    op.drop_index(op.f('ix_service_inbound_api_history_service_id'), table_name='service_inbound_api_history')
    op.drop_table('service_inbound_api_history')