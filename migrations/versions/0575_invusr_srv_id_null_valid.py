"""
Create Date: 2026-10-02 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0575_invusr_srv_id_null_valid"
down_revision = "0574_invusr_srv_id_null_cnstr"


def upgrade():
    op.execute(
        "ALTER TABLE invited_users "
        "VALIDATE CONSTRAINT ck_invited_users_service_id_not_null;"
    )
    op.execute("ALTER TABLE invited_users ALTER COLUMN service_id SET NOT NULL;")
    op.execute(
        "ALTER TABLE invited_users DROP CONSTRAINT IF EXISTS "
        "ck_invited_users_service_id_not_null;"
    )


def downgrade():
    op.execute(
        "-- squawk-ignore require-timeout-settings\n"
        "ALTER TABLE invited_users "
        "ADD CONSTRAINT ck_invited_users_service_id_not_null "
        "CHECK (service_id IS NOT NULL) NOT VALID;"
    )
    op.execute("ALTER TABLE invited_users ALTER COLUMN service_id DROP NOT NULL;")
