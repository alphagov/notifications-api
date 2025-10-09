"""
Create Date: 2025-09-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0524_jobs_xstats_dep"
down_revision = "0523_invited_users_xstats_dep"


def upgrade():
    op.execute(
        "CREATE STATISTICS st_dep_jobs_service_id_created_by_id (dependencies) ON service_id, created_by_id FROM jobs"
    )


def downgrade():
    op.execute("DROP STATISTICS st_dep_jobs_service_id_created_by_id")
