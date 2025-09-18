"""
Create Date: 2025-09-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0532_unsub_req_xstats_dep"
down_revision = "0531_templates_hist_xstats_dep"


def upgrade():
    op.execute(
        "CREATE STATISTICS st_dep_unsub_req_service_id_unsub_req_rpt_id (dependencies) ON service_id, unsubscribe_request_report_id FROM unsubscribe_request"
    )
    op.execute(
        "CREATE STATISTICS st_dep_unsub_req_service_id_tpt_id_ntfcn_id (dependencies) ON service_id, template_id, notification_id FROM unsubscribe_request"
    )


def downgrade():
    op.execute("DROP STATISTICS st_dep_unsub_req_service_id_unsub_req_rpt_id")
    op.execute("DROP STATISTICS st_dep_unsub_req_service_id_tpt_id_ntfcn_id")
