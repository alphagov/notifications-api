"""
Create Date: 2025-09-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0520_inbound_sms_xstats_dep"
down_revision = "0519_drop_n_hist_api_key_index"


def upgrade():
    op.execute(
        "CREATE STATISTICS st_dep_inb_sms_service_id_ntfy_num_provider (dependencies) ON service_id, notify_number, provider FROM inbound_sms"
    )


def downgrade():
    op.execute("DROP STATISTICS st_dep_inb_sms_service_id_ntfy_num_provider")
