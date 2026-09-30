"""
Create Date: 2026-09-30 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0570_jobs_tpt_id_null_cnstr"
down_revision = "0569_oup_org_id_null_valid"


def upgrade():
    op.execute(
        "-- squawk-ignore require-timeout-settings\n"
        "ALTER TABLE jobs "
        "ADD CONSTRAINT ck_jobs_template_id_not_null "
        "CHECK (template_id IS NOT NULL) NOT VALID;"
    )


def downgrade():
    op.execute(
        "ALTER TABLE jobs DROP CONSTRAINT IF EXISTS ck_jobs_template_id_not_null;"
    )
