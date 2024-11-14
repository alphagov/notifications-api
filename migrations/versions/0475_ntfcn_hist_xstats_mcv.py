"""
Create Date: 2024-11-13T16:34
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0475_ntfcn_hist_xstats_mcv"
down_revision = "0474_ntfcn_hist_xstats_dep"


def upgrade():
    op.execute(
        "CREATE STATISTICS st_mcv_notification_history_ntfcn_type_status (mcv) ON notification_type, notification_status FROM notification_history"
    )
    op.execute(
        "CREATE STATISTICS st_mcv_notification_history_service_id_key_type (mcv) ON service_id, key_type FROM notification_history"
    )
    op.execute(
        "CREATE STATISTICS st_mcv_notification_history_service_id_ntfcn_type (mcv) ON service_id, notification_type FROM notification_history"
    )


def downgrade():
    op.execute("DROP STATISTICS st_mcv_notification_history_ntfcn_type_status")
    op.execute("DROP STATISTICS st_mcv_notification_history_service_id_key_type")
    op.execute("DROP STATISTICS st_mcv_notification_history_service_id_ntfcn_type")
