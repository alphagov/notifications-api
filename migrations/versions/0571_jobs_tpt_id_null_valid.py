"""
Create Date: 2026-09-30 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0571_jobs_tpt_id_null_valid"
down_revision = "0570_jobs_tpt_id_null_cnstr"


def upgrade():
    op.execute(
        "ALTER TABLE jobs "
        "VALIDATE CONSTRAINT ck_jobs_template_id_not_null;"
    )
    op.execute("ALTER TABLE jobs ALTER COLUMN template_id SET NOT NULL;")
    op.execute(
        "ALTER TABLE jobs DROP CONSTRAINT IF EXISTS "
        "ck_jobs_template_id_not_null;"
    )


def downgrade():
    op.execute(
        "-- squawk-ignore require-timeout-settings\n"
        "ALTER TABLE jobs "
        "ADD CONSTRAINT ck_jobs_template_id_not_null "
        "CHECK (template_id IS NOT NULL) NOT VALID;"
    )
    op.execute("ALTER TABLE jobs ALTER COLUMN template_id DROP NOT NULL;")
