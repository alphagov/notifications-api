"""
Create Date: 2024-11-12 17:02:20.993114
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0473_jobs_xstats_deps"
down_revision = "0472_ft_ntfcn_status_xstats_deps"


def upgrade():
    op.execute(
        "CREATE STATISTICS st_dep_jobs_service_id_template_id (dependencies) ON service_id, template_id FROM jobs"
    )
    op.execute(
        "CREATE STATISTICS st_dep_jobs_service_id_contact_list_id (dependencies) ON service_id, contact_list_id FROM jobs"
    )


def downgrade():
    op.execute("DROP STATISTICS st_dep_jobs_service_id_contact_list_id")
    op.execute("DROP STATISTICS st_dep_jobs_service_id_template_id")
