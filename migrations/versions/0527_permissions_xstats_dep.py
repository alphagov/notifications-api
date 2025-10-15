"""
Create Date: 2025-09-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0527_permissions_xstats_dep"
down_revision = "0526_ntfcn_hist_xstats_dep"


def upgrade():
    op.execute(
        "CREATE STATISTICS st_dep_permissions_service_id_user_id (dependencies) ON service_id, user_id FROM permissions"
    )


def downgrade():
    op.execute("DROP STATISTICS st_dep_permissions_service_id_user_id")
