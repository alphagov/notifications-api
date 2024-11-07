"""
Create Date: 2024-11-06 13:51:53.222714
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0469_notifications_xstats_dep"
down_revision = "0468"


def upgrade():
    op.execute(
        "CREATE STATISTICS st_dep_notifications_service_id_api_key_id (dependencies) ON service_id, api_key_id FROM notifications"
    )
    op.execute(
        "CREATE STATISTICS st_dep_notifications_service_id_job_id (dependencies) ON service_id, job_id FROM notifications"
    )
    op.execute(
        "CREATE STATISTICS st_dep_notifications_service_id_template_id (dependencies) ON service_id, template_id FROM notifications"
    )
    op.execute(
        "CREATE STATISTICS st_dep_notifications_template_id_notification_type (dependencies) ON template_id, notification_type FROM notifications"
    )


def downgrade():
    op.execute("DROP STATISTICS st_dep_notifications_service_id_api_key_id")
    op.execute("DROP STATISTICS st_dep_notifications_service_id_job_id")
    op.execute("DROP STATISTICS st_dep_notifications_service_id_template_id")
    op.execute("DROP STATISTICS st_dep_notifications_template_id_notification_type")
