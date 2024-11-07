"""
Create Date: 2024-11-06 16:25:17.550808
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0470_notifications_xstats_mcv"
down_revision = "0469_notifications_xstats_dep"


def upgrade():
    op.execute(
        "CREATE STATISTICS st_mcv_notifications_notification_type_status (mcv) ON notification_type, notification_status FROM notifications"
    )
    op.execute(
        "CREATE STATISTICS st_mcv_notifications_service_id_key_type (mcv) ON service_id, key_type FROM notifications"
    )
    op.execute(
        "CREATE STATISTICS st_mcv_notifications_service_id_notification_type (mcv) ON service_id, notification_type FROM notifications"
    )


def downgrade():
    op.execute("DROP STATISTICS st_mcv_notifications_notification_type_status")
    op.execute("DROP STATISTICS st_mcv_notifications_service_id_key_type")
    op.execute("DROP STATISTICS st_mcv_notifications_service_id_notification_type")
