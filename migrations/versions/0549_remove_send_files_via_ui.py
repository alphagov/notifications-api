"""

Create Date: 2026-04-23 14:00:00.0
Revision ID: 0549_remove_send_files_via_ui
Revises: "0548_letter_rates_from_3_5_26"

"""

revision = "0549_remove_send_files_via_ui"
down_revision = "0548_letter_rates_from_3_5_26"

from alembic import op
from sqlalchemy import text

def upgrade():
    op.execute("DELETE FROM service_permissions WHERE permission = 'send_files_via_ui'")
    op.execute("DELETE FROM service_permission_types WHERE name = 'send_files_via_ui'")

def downgrade():
    op.execute("INSERT INTO service_permission_types VALUES ('send_files_via_ui')")

