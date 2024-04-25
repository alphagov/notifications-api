"""

Revision ID: 0337_broadcast_msg_api
Revises: 0336_broadcast_msg_content_2
Create Date: 2020-12-04 15:06:22.544803

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0337_broadcast_msg_api"
down_revision = "0336_broadcast_msg_content_2"


def upgrade():
    op.alter_column("broadcast_message", "created_by_id", nullable=True)
    op.add_column("broadcast_message", sa.Column("api_key_id", postgresql.UUID(), nullable=True))
    op.create_foreign_key(None, "broadcast_message", "api_keys", ["api_key_id"], ["id"])
    op.add_column("broadcast_message", sa.Column("reference", sa.String(length=255), nullable=True))


def downgrade():
    op.alter_column("broadcast_message", "created_by_id", nullable=False)
    op.drop_column("broadcast_message", "api_key_id")
    op.add_column("broadcast_message", "reference")
