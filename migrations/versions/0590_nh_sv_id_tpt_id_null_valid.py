"""
Create Date: 2026-11-13 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0590_nh_sv_id_tpt_id_null_valid"
down_revision = "0589_nh_sv_id_tpt_id_null_cnstr"


def upgrade():
    op.execute(
        "ALTER TABLE notification_history "
        "VALIDATE CONSTRAINT ck_notification_history_service_id_template_id_not_null;"
    )
    op.execute("ALTER TABLE notification_history ALTER COLUMN service_id SET NOT NULL;")
    op.execute("ALTER TABLE notification_history ALTER COLUMN template_id SET NOT NULL;")
    op.execute(
        "-- squawk-ignore ban-drop-constraint\n"
        "ALTER TABLE notification_history DROP CONSTRAINT IF EXISTS "
        "ck_notification_history_service_id_template_id_not_null;"
    )


def downgrade():
    op.execute(
        "-- squawk-ignore require-timeout-settings\n"
        "ALTER TABLE notification_history "
        "ADD CONSTRAINT ck_notification_history_service_id_template_id_not_null "
        "CHECK (service_id IS NOT NULL AND template_id IS NOT NULL) NOT VALID;"
    )
    op.execute("ALTER TABLE notification_history ALTER COLUMN template_id DROP NOT NULL;")
    op.execute("ALTER TABLE notification_history ALTER COLUMN service_id DROP NOT NULL;")
