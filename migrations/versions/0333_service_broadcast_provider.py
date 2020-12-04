"""

Revision ID: 0333_service_broadcast_provider
Revises: 0332_broadcast_provider_msg
Create Date: 2020-12-01 17:03:18.209780

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0333_service_broadcast_provider'
down_revision = '0332_broadcast_provider_msg'


def upgrade():
    op.create_table(
        'service_broadcast_provider_restriction',
        sa.Column('service_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ),
        sa.PrimaryKeyConstraint('service_id')
    )


def downgrade():
    op.drop_table('service_broadcast_provider_restriction')
