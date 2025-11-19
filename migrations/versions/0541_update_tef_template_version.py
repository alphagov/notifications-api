"""
Create Date: 2025-11-19 00:00:00.000000
"""

from alembic import op

revision = "0541_update_tef_template_version"
down_revision = "0540_send_files_via_ui"


def upgrade():
    op.execute("ALTER TABLE template_email_files RENAME COLUMN template_version to template_version_on_update")


def downgrade():
    op.execute("ALTER TABLE template_email_files RENAME COLUMN template_version_on_update to template_version")