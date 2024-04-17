"""

Revision ID: 0359_more_permissions
Revises: 0358_operator_channel
Create Date: 2021-06-15 17:47:16.871071

"""

import sqlalchemy as sa
from alembic import op

revision = "0359_more_permissions"
down_revision = "0358_operator_channel"

enum_name = "permission_types"
tmp_name = "tmp_" + enum_name

old_options = (
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
old_type = sa.Enum(*old_options, name=enum_name)


def upgrade():
    # ALTER TYPE must be run outside of a transaction block (see link below for details)
    # https://alembic.sqlalchemy.org/en/latest/api/runtime.html#alembic.runtime.migration.MigrationContext.autocommit_block
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE permission_types ADD VALUE 'create_broadcasts'")
        op.execute("ALTER TYPE permission_types ADD VALUE 'approve_broadcasts'")
        op.execute("ALTER TYPE permission_types ADD VALUE 'cancel_broadcasts'")
        op.execute("ALTER TYPE permission_types ADD VALUE 'reject_broadcasts'")


def downgrade():
    op.execute(
        "DELETE FROM permissions WHERE permission in "
        "('create_broadcasts', 'approve_broadcasts', 'cancel_broadcasts', 'reject_broadcasts')"
    )

    op.execute(f"ALTER TYPE {enum_name} RENAME TO {tmp_name}")
    old_type.create(op.get_bind())
    op.execute(f"ALTER TABLE permissions ALTER COLUMN permission TYPE {enum_name} USING permission::text::{enum_name}")
    op.execute(f"DROP TYPE {tmp_name}")
