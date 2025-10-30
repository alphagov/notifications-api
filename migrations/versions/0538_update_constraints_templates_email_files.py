"""
Create Date: 2025-10-30 15:00:54.790811
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0538_update_constraints_templates_email_files'
down_revision = '0537_templates_email_files'


def upgrade():
    op.execute("ALTER TABLE template_email_files ALTER COLUMN archived_by_id DROP NOT NULL")
    op.execute("ALTER TABLE template_email_files_history ALTER COLUMN archived_by_id DROP NOT NULL")


def downgrade():
    op.execute("ALTER TABLE template_email_files ALTER COLUMN archived_by_id SET NOT NULL")
    op.execute("ALTER TABLE template_email_files_history ALTER COLUMN archived_by_id SET NOT NULL")
