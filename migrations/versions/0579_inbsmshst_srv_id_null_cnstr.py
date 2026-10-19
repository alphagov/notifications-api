"""
Create Date: 2026-10-18 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0579_inbsmshst_srv_id_null_cnstr"
down_revision = "0578_drop_ft_service_stats"


def upgrade():
    op.execute(
        "-- squawk-ignore require-timeout-settings\n"
        "ALTER TABLE inbound_sms_history "
        "ADD CONSTRAINT ck_inbound_sms_history_service_id_not_null "
        "CHECK (service_id IS NOT NULL) NOT VALID;"
    )


def downgrade():
    op.execute(
        "ALTER TABLE inbound_sms_history DROP CONSTRAINT IF EXISTS ck_inbound_sms_history_service_id_not_null;"
    )
