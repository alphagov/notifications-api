"""
Create Date: 2026-03-19 11:15:54.687868
"""

from alembic import op

revision = '0546_update_permissions_enum'
down_revision = '0545_add_pending_column'


def upgrade():
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE permission_types ADD VALUE IF NOT EXISTS 'send_files_via_ui'")


def downgrade():
    pass
