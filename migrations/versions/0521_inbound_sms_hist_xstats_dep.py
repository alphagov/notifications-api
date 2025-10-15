"""
Create Date: 2025-09-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0521_inbound_sms_hist_xstats_dep"
down_revision = "0520_launch_token_bucket"


def upgrade():
    op.execute(
        "CREATE STATISTICS st_dep_inb_sms_hist_service_id_ntfy_num_provider (dependencies) ON service_id, notify_number, provider FROM inbound_sms_history"
    )


def downgrade():
    op.execute("DROP STATISTICS st_dep_inb_sms_hist_service_id_ntfy_num_provider")
