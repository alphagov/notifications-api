"""
Create Date: 2026-10-02 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0574_invusr_srv_id_null_cnstr"
down_revision = "0573_ntf_sv_id_tpt_id_null_valid"


def upgrade():
    op.execute(
        "-- squawk-ignore require-timeout-settings\n"
        "ALTER TABLE invited_users "
        "ADD CONSTRAINT ck_invited_users_service_id_not_null "
        "CHECK (service_id IS NOT NULL) NOT VALID;"
    )


def downgrade():
    op.execute(
        "ALTER TABLE invited_users DROP CONSTRAINT IF EXISTS ck_invited_users_service_id_not_null;"
    )
