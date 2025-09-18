"""
Create Date: 2025-09-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0530_template_folder_xstats_dep"
down_revision = "0529_templates_xstats_dep"


def upgrade():
    op.execute(
        "CREATE STATISTICS st_dep_template_folder_service_id_parent_id (dependencies) ON service_id, parent_id FROM template_folder"
    )


def downgrade():
    op.execute("DROP STATISTICS st_dep_template_folder_service_id_parent_id")
