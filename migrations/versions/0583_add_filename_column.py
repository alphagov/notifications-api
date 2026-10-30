"""
Create Date: 2026-10-29 10:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0583_add_filename_column"
down_revision = "0582_rename_sent_files_filename"

def upgrade():
    op.execute("ALTER TABLE sent_files ADD COLUMN filename text")

def downgrade():
    op.execute("ALTER TABLE sent_files DROP COLUMN filename")