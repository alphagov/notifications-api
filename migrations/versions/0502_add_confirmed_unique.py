"""
Create Date: 2025-05-23 15:34:27.333353
"""

import sqlalchemy as sa
from alembic import op


revision = '0502_add_confirmed_unique'
down_revision = '0501_drop_inbound_api_table'


confirmed_unique = "confirmed_unique"


def upgrade():
    op.add_column("services", sa.Column(confirmed_unique, sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("services_history", sa.Column(confirmed_unique, sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("services_history", confirmed_unique)
    op.drop_column("services", confirmed_unique)
