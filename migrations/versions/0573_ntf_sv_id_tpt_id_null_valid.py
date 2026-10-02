"""
Create Date: 2026-10-02 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0573_ntf_sv_id_tpt_id_null_valid"
down_revision = "0572_ntf_sv_id_tpt_id_null_cnstr"


def upgrade():
    op.execute(
        "ALTER TABLE notifications "
        "VALIDATE CONSTRAINT ck_notifications_service_id_template_id_not_null;"
    )
    op.execute("ALTER TABLE notifications ALTER COLUMN service_id SET NOT NULL;")
    op.execute("ALTER TABLE notifications ALTER COLUMN template_id SET NOT NULL;")
    op.execute(
        "ALTER TABLE notifications DROP CONSTRAINT IF EXISTS "
        "ck_notifications_service_id_template_id_not_null;"
    )


def downgrade():
    op.execute(
        "-- squawk-ignore require-timeout-settings\n"
        "ALTER TABLE notifications "
        "ADD CONSTRAINT ck_notifications_service_id_template_id_not_null "
        "CHECK (service_id IS NOT NULL AND template_id IS NOT NULL) NOT VALID;"
    )
    op.execute("ALTER TABLE notifications ALTER COLUMN template_id DROP NOT NULL;")
    op.execute("ALTER TABLE notifications ALTER COLUMN service_id DROP NOT NULL;")
