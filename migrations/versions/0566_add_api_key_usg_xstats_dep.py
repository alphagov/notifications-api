"""
Create Date: 2026-09-18 14:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = '0566_add_api_key_usg_xstats_dep'
down_revision = '0565_add_api_key_usage_table'


def upgrade():
    op.execute(
        "CREATE STATISTICS st_dep_api_key_usage_service_id_api_key_id (dependencies) ON service_id, api_key_id FROM api_key_usage"
    )


def downgrade():
    op.execute("DROP STATISTICS st_dep_api_key_usage_service_id_api_key_id")
