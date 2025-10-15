"""
Create Date: 2025-09-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0522_inv_org_usrs_xstats_dep"
down_revision = "0521_inbound_sms_hist_xstats_dep"


def upgrade():
    op.execute(
        "CREATE STATISTICS st_dep_inv_org_users_inv_by_id_org_id (dependencies) ON invited_by_id, organisation_id FROM invited_organisation_users"
    )


def downgrade():
    op.execute("DROP STATISTICS st_dep_inv_org_users_inv_by_id_org_id")
