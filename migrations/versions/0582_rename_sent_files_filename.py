"""
Create Date: 2026-10-29 10:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0582_rename_sent_files_filename"
down_revision = "0581_create_replication_slot"

def upgrade():
    op.execute("ALTER TABLE sent_files RENAME COLUMN filename TO placeholder")

def downgrade():
    op.execute("ALTER TABLE sent_files RENAME COLUMN placeholder TO filename")