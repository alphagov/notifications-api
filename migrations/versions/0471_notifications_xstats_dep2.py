"""
Create Date: 2024-11-08 13:25:26.784680
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0471_notifications_xstats_dep2"
down_revision = "0470_notifications_xstats_mcv"


def upgrade():
    op.execute("DROP STATISTICS st_dep_notifications_template_id_notification_type")
    op.execute(
        "CREATE STATISTICS st_dep_notifications_job_id_template_id_notification_type (dependencies) ON job_id, template_id, notification_type FROM notifications"
    )


def downgrade():
    op.execute("DROP STATISTICS st_dep_notifications_job_id_template_id_notification_type")
    op.execute(
        "CREATE STATISTICS st_dep_notifications_template_id_notification_type (dependencies) ON template_id, notification_type FROM notifications"
    )
