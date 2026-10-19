"""
Create Date: 2026-10-18 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0580_inbsmshst_srv_id_null_valid"
down_revision = "0579_inbsmshst_srv_id_null_cnstr"


def upgrade():
    op.execute(
        "ALTER TABLE inbound_sms_history "
        "VALIDATE CONSTRAINT ck_inbound_sms_history_service_id_not_null;"
    )
    op.execute("ALTER TABLE inbound_sms_history ALTER COLUMN service_id SET NOT NULL;")
    op.execute(
        "ALTER TABLE inbound_sms_history DROP CONSTRAINT IF EXISTS "
        "ck_inbound_sms_history_service_id_not_null;"
    )


def downgrade():
    op.execute(
        "-- squawk-ignore require-timeout-settings\n"
        "ALTER TABLE inbound_sms_history "
        "ADD CONSTRAINT ck_inbound_sms_history_service_id_not_null "
        "CHECK (service_id IS NOT NULL) NOT VALID;"
    )
    op.execute("ALTER TABLE inbound_sms_history ALTER COLUMN service_id DROP NOT NULL;")
