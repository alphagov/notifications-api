"""
Create Date: 2026-09-27 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0568_oup_org_id_null_cnstr"
down_revision = "0567_notification_to_file_table"


def upgrade():
    op.execute(
        "-- squawk-ignore require-timeout-settings\n"
        "ALTER TABLE organisation_user_permissions "
        "ADD CONSTRAINT ck_organisation_user_permissions_organisation_id_not_null "
        "CHECK (organisation_id IS NOT NULL) NOT VALID;"
    )


def downgrade():
    op.execute(
        "ALTER TABLE organisation_user_permissions DROP CONSTRAINT IF EXISTS ck_organisation_user_permissions_organisation_id_not_null;"
    )
