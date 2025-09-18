"""
Create Date: 2025-09-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0534_api_keys_xstats_dep"
down_revision = "0533_unsub_req_hist_xstats_dep"


def upgrade():
    op.execute(
        "CREATE STATISTICS st_dep_api_keys_service_id_created_by_id (dependencies) ON service_id, created_by_id FROM api_keys"
    )


def downgrade():
    op.execute("DROP STATISTICS st_dep_api_keys_service_id_created_by_id")
