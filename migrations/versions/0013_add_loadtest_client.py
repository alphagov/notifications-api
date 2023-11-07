"""empty message

Revision ID: 0013_add_loadtest_client
Revises: 0012_complete_provider_details
Create Date: 2016-05-05 09:14:29.328841

"""

# revision identifiers, used by Alembic.
revision = "0013_add_loadtest_client"
down_revision = "0012_complete_provider_details"

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


def upgrade():
    op.execute(
        "INSERT INTO provider_details (id, display_name, identifier, priority, notification_type, active) values ('{}', 'Loadtesting', 'loadtesting', 30, 'sms', true)".format(
            str(uuid.uuid4())
        )
    )


def downgrade():
    op.drop_table("provider_details")
