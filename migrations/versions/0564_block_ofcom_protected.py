"""
Create Date: 2026-09-09 00:00:00.000000
"""

from alembic import op

revision = "0564_block_ofcom_protected"
down_revision = "0563_confirmed_service_name_col"


def upgrade():
    op.execute("INSERT INTO service_permission_types VALUES ('block_ofcom_protected_block')")


def downgrade():
    op.execute("DELETE FROM service_permissions WHERE permission = 'block_ofcom_protected_block'")
    op.execute("DELETE FROM service_permission_types WHERE name = 'block_ofcom_protected_block'")