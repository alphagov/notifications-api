"""
Create Date: 2025-11-12 00:00:00.000000
"""

from alembic import op

revision = "0540_send_files_via_ui"
down_revision = "0539_update_constraints_tef"


def upgrade():
    op.execute("INSERT INTO service_permission_types VALUES ('send_files_via_ui')")


def downgrade():
    op.execute("DELETE FROM service_permissions WHERE permission = 'send_files_via_ui'")
    op.execute("DELETE FROM service_permission_types WHERE name = 'send_files_via_ui'")