"""
Create Date: 2024-10-01 11:08:46.900469
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0467_remove_broadcast_perms"
down_revision = "0466_delete_broadcast_tables"

# code copied from 0359 (but switched upgrade/downgrade)
enum_name = "permission_types"
tmp_name = "tmp_" + enum_name

new_options = (
    "manage_users",
    "manage_templates",
    "manage_settings",
    "send_texts",
    "send_emails",
    "send_letters",
    "manage_api_keys",
    "platform_admin",
    "view_activity",
)
new_type = sa.Enum(*new_options, name=enum_name)


def upgrade():
    op.execute(
        "DELETE FROM permissions WHERE permission in "
        "('create_broadcasts', 'approve_broadcasts', 'cancel_broadcasts', 'reject_broadcasts')"
    )

    op.execute(f"ALTER TYPE {enum_name} RENAME TO {tmp_name}")
    new_type.create(op.get_bind())
    op.execute(f"ALTER TABLE permissions ALTER COLUMN permission TYPE {enum_name} USING permission::text::{enum_name}")
    op.execute(f"DROP TYPE {tmp_name}")


def downgrade():
    # ALTER TYPE must be run outside of a transaction block (see link below for details)
    # https://alembic.sqlalchemy.org/en/latest/api/runtime.html#alembic.runtime.migration.MigrationContext.autocommit_block
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE permission_types ADD VALUE 'create_broadcasts'")
        op.execute("ALTER TYPE permission_types ADD VALUE 'approve_broadcasts'")
        op.execute("ALTER TYPE permission_types ADD VALUE 'cancel_broadcasts'")
        op.execute("ALTER TYPE permission_types ADD VALUE 'reject_broadcasts'")
