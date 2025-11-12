"""
Create Date: 2025-10-30 15:00:54.790811
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0539_update_constraints_tef'
down_revision = '0538_remove_token_bucket_perm'


def upgrade():
    op.execute("ALTER TABLE template_email_files ALTER COLUMN archived_by_id DROP NOT NULL")
    op.execute("ALTER TABLE template_email_files_history ALTER COLUMN archived_by_id DROP NOT NULL")


def downgrade():
    op.execute("ALTER TABLE template_email_files ALTER COLUMN archived_by_id SET NOT NULL")
    op.execute("ALTER TABLE template_email_files_history ALTER COLUMN archived_by_id SET NOT NULL")
