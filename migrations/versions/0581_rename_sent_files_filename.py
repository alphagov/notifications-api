"""
Create Date: 2026-10-29 10:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0581_rename_sent_files_filename"
down_revision = "0580_inbsmshst_srv_id_null_valid"

def upgrade():
    op.execute("ALTER TABLE sent_files RENAME COLUMN filename TO placeholder")

def downgrade():
    op.execute("ALTER TABLE sent_files RENAME COLUMN placeholder TO filename")