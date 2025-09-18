"""
Create Date: 2025-09-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0526_ntfcn_hist_xstats_dep"
down_revision = "0525_notifications_xstats_dep"


def upgrade():
    op.execute(
        "CREATE STATISTICS st_dep_notification_history_ntfcn_type_postage (dependencies) ON notification_type, postage FROM notification_history"
    )
    op.execute(
        "CREATE STATISTICS st_dep_notification_history_ntfcn_type_sent_by (dependencies) ON notification_type, sent_by FROM notification_history"
    )
    op.execute(
        "CREATE STATISTICS st_dep_notification_history_sent_by_postage (dependencies) ON sent_by, postage FROM notification_history"
    )
    op.execute(
        "CREATE STATISTICS st_dep_notification_history_ntfcn_type_doc_dl (dependencies) ON notification_type, document_download_count FROM notification_history"
    )
    op.execute(
        "CREATE STATISTICS st_dep_notification_history_phone_prefix_intnl (dependencies) ON phone_prefix, international FROM notification_history"
    )
    op.execute(
        "CREATE STATISTICS st_dep_notification_history_ntfcn_type_intnl (dependencies) ON notification_type, international FROM notification_history"
    )
    op.execute(
        "CREATE STATISTICS st_dep_notification_history_service_id_cby_id (dependencies) ON service_id, created_by_id FROM notification_history"
    )
    op.execute(
        "CREATE STATISTICS st_dep_notification_history_ntfcn_type_phone_prefix (dependencies) ON notification_type, phone_prefix FROM notification_history"
    )


def downgrade():
    op.execute("DROP STATISTICS st_dep_notification_history_ntfcn_type_postage")
    op.execute("DROP STATISTICS st_dep_notification_history_ntfcn_type_sent_by")
    op.execute("DROP STATISTICS st_dep_notification_history_sent_by_postage")
    op.execute("DROP STATISTICS st_dep_notification_history_ntfcn_type_doc_dl")
    op.execute("DROP STATISTICS st_dep_notification_history_phone_prefix_intnl")
    op.execute("DROP STATISTICS st_dep_notification_history_ntfcn_type_intnl")
    op.execute("DROP STATISTICS st_dep_notification_history_service_id_cby_id")
    op.execute("DROP STATISTICS st_dep_notification_history_ntfcn_type_phone_prefix")
