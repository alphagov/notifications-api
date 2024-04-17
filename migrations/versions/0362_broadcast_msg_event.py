"""

Revision ID: 0362_broadcast_msg_event
Revises: 0361_new_user_bcast_permissions
Create Date: 2020-12-04 15:06:22.544803

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0362_broadcast_msg_event"
down_revision = "0361_new_user_bcast_permissions"


def upgrade():
    op.add_column("broadcast_message", sa.Column("cap_event", sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column("broadcast_message", "cap_event")
