"""
Create Date: 2024-11-13T16:34
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0474_ntfcn_hist_xstats_dep"
down_revision = "0473_jobs_xstats_deps"


def upgrade():
    op.execute(
        "CREATE STATISTICS st_dep_notification_history_service_id_api_key_id (dependencies) ON service_id, api_key_id FROM notification_history"
    )
    op.execute(
        "CREATE STATISTICS st_dep_notification_history_service_id_job_id (dependencies) ON service_id, job_id FROM notification_history"
    )
    op.execute(
        "CREATE STATISTICS st_dep_notification_history_service_id_tpt_id (dependencies) ON service_id, template_id FROM notification_history"
    )
    op.execute(
        "CREATE STATISTICS st_dep_notification_history_job_id_tpt_id_ntfcn_type (dependencies) ON job_id, template_id, notification_type FROM notification_history"
    )


def downgrade():
    op.execute("DROP STATISTICS st_dep_notification_history_service_id_api_key_id")
    op.execute("DROP STATISTICS st_dep_notification_history_service_id_job_id")
    op.execute("DROP STATISTICS st_dep_notification_history_service_id_tpt_id")
    op.execute("DROP STATISTICS st_dep_notification_history_job_id_tpt_id_ntfcn_type")
