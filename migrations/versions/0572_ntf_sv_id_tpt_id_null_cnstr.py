"""
Create Date: 2026-10-02 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0572_ntf_sv_id_tpt_id_null_cnstr"
down_revision = "0571_jobs_tpt_id_null_valid"


def upgrade():
    op.execute(
        "-- squawk-ignore require-timeout-settings\n"
        "ALTER TABLE notifications "
        "ADD CONSTRAINT ck_notifications_service_id_template_id_not_null "
        "CHECK (service_id IS NOT NULL AND template_id IS NOT NULL) NOT VALID;"
    )


def downgrade():
    op.execute(
        "ALTER TABLE notifications DROP CONSTRAINT IF EXISTS ck_notifications_service_id_template_id_not_null;"
    )
