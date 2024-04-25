"""

Revision ID: 0354_government_channel
Revises: 0353_broadcast_provider_not_null
Create Date: 2021-05-11 16:17:12.479191

"""

from alembic import op

revision = "0354_government_channel"
down_revision = "0353_broadcast_provider_not_null"


def upgrade():
    op.execute("INSERT INTO broadcast_channel_types VALUES ('government')")


def downgrade():
    # This can't be downgraded if there are rows in service_broadcast_settings which
    # have the channel set to government or if broadcasts have already been sent on the
    # government channel - it would break foreign key constraints.
    op.execute("DELETE FROM broadcast_channel_types WHERE name = 'government'")
