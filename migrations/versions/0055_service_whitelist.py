"""add service whitelist table

Revision ID: 0055_service_whitelist
Revises: 0054_perform_drop_status_column
Create Date: 2016-09-20 12:12:30.838095

"""

# revision identifiers, used by Alembic.
revision = '0055_service_whitelist'
down_revision = '0054_perform_drop_status_column'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.create_table('service_whitelist',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('service_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('recipient_type', sa.Enum('mobile', 'email', name='recipient_type'), nullable=False),
        sa.Column('recipient', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_service_whitelist_service_id'), 'service_whitelist', ['service_id'], unique=False)


def downgrade():
    op.drop_table('service_whitelist')
