"""
Create Date: 2024-11-12 13:52:45.602326
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0472_ft_ntfcn_status_xstats_deps"
down_revision = "0471_notifications_xstats_dep2"


def upgrade():
    op.execute(
        "CREATE STATISTICS st_dep_ft_notification_status_service_id_job_id (dependencies) ON service_id, job_id FROM ft_notification_status"
    )
    op.execute(
        "CREATE STATISTICS st_dep_ft_notification_status_service_id_template_id (dependencies) ON service_id, template_id FROM ft_notification_status"
    )
    op.execute(
        "CREATE STATISTICS st_dep_ft_notification_status_job_id_template_id_ntfcn_type (dependencies) ON job_id, template_id, notification_type FROM ft_notification_status"
    )


def downgrade():
    op.execute("DROP STATISTICS st_dep_ft_notification_status_job_id_template_id_ntfcn_type")
    op.execute("DROP STATISTICS st_dep_ft_notification_status_service_id_template_id")
    op.execute("DROP STATISTICS st_dep_ft_notification_status_service_id_job_id")
