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
    op.create_table(
        'service_inbound_api',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('service_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('url', sa.String, nullable=False),
        sa.Column('bearer_token', sa.String, nullable=False),

        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_service_inbound_api_id'), 'service_inbound_api', ['service_id'], unique=False)


def downgrade():
    op.drop_table("service_inbound_api")
