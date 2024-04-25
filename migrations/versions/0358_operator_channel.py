"""

Revision ID: 0358_operator_channel
Revises: 0357_validate_constraint
Create Date: 2021-06-09 13:44:12.479191

"""

from alembic import op

revision = "0358_operator_channel"
down_revision = "0357_validate_constraint"


def upgrade():
    op.execute("INSERT INTO broadcast_channel_types VALUES ('operator')")


def downgrade():
    # This can't be downgraded if there are rows in service_broadcast_settings which
    # have the channel set to operator or if broadcasts have already been sent on the
    # operator channel - it would break foreign key constraints.
    op.execute("DELETE FROM broadcast_channel_types WHERE name = 'operator'")
