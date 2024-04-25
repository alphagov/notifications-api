"""

Revision ID: 0353_broadcast_provider_not_null
Revises: 0352_broadcast_provider_types
Create Date: 2021-05-10 15:06:40.046786

"""

import sqlalchemy as sa
from alembic import op

revision = "0353_broadcast_provider_not_null"
down_revision = "0352_broadcast_provider_types"


def upgrade():
    op.execute("UPDATE service_broadcast_settings SET provider = 'all' WHERE provider is null")
    op.alter_column("service_broadcast_settings", "provider", existing_type=sa.VARCHAR(), nullable=False)


def downgrade():
    op.alter_column("service_broadcast_settings", "provider", existing_type=sa.VARCHAR(), nullable=True)
    op.execute("UPDATE service_broadcast_settings SET provider = null WHERE provider = 'all'")
