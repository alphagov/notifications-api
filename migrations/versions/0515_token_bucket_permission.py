"""
Create Date: 2025-08-27 00:00:00.000000
"""

from alembic import op

revision = "0515_token_bucket_permission"
down_revision = "0514_drop_process_type_3"


def upgrade():
    op.execute("INSERT INTO service_permission_types VALUES ('token_bucket')")


def downgrade():
    op.execute("DELETE FROM service_permissions WHERE permission = 'token_bucket'")
    op.execute("DELETE FROM service_permission_types WHERE name = 'token_bucket'")
