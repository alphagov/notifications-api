"""
Create Date: 2025-08-29 08:16:36.817900
"""

from alembic import op

revision = '0516_remove_broadcast_permission'
down_revision = '0515_token_bucket_permission'


def upgrade():
    # no services will have this permission (it will have been removed in previous migrations),
    # but leaving as a precaution or in case this migration gets copied
    op.execute("DELETE from service_permissions where permission = 'broadcast'")
    op.execute("DELETE from service_permission_types where name = 'broadcast'")


def downgrade():
    op.execute("INSERT INTO service_permission_types values ('broadcast')")
