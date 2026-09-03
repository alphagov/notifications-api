"""
Create Date: 2026-09-03 13:45:41.137308
"""

from alembic import op
import sqlalchemy as sa

revision = '0563_confirmed_service_name_col'
down_revision = '0562_enable_replica_id_index'


def upgrade():
    op.add_column("services", sa.Column("confirmed_service_name", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("services_history", sa.Column("confirmed_service_name", sa.Boolean(), nullable=False, server_default=sa.false()))

def downgrade():
    op.drop_column("services_history", "confirmed_service_name")
    op.drop_column("services", "confirmed_service_name")
