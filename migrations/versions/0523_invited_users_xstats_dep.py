"""
Create Date: 2025-09-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0523_invited_users_xstats_dep"
down_revision = "0522_inv_org_usrs_xstats_dep"


def upgrade():
    op.execute(
        "CREATE STATISTICS st_dep_inv_users_user_id_service_id (dependencies) ON user_id, service_id FROM invited_users"
    )


def downgrade():
    op.execute("DROP STATISTICS st_dep_inv_users_user_id_service_id")
