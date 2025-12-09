"""
Create Date: 2025-12-09 00:00:00.000000
"""

from alembic import op

revision = "0541_unique_filename_constraint"
down_revision = "0540_send_files_via_ui"


def upgrade():
    op.execute("ALTER TABLE template_email_files ADD CONSTRAINT unique_filenames UNIQUE (template_id, filename)")


def downgrade():
    op.execute("ALTER TABLE template_email_files DROP CONSTRAINT unique_filenames")