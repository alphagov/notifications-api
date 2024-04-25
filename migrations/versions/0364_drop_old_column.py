"""

Revision ID: 0364_drop_old_column
Revises: 0363_cancelled_by_api_key
Create Date: 2022-01-25 18:05:27.750234

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0364_drop_old_column"
down_revision = "0363_cancelled_by_api_key"


def upgrade():
    # move data over
    op.execute("UPDATE broadcast_message SET created_by_api_key_id=api_key_id WHERE created_by_api_key_id IS NULL")
    op.create_check_constraint(
        "ck_broadcast_message_created_by_not_null",
        "broadcast_message",
        "created_by_id is not null or created_by_api_key_id is not null",
    )
    op.drop_column("broadcast_message", "api_key_id")


def downgrade():
    op.add_column("broadcast_message", sa.Column("api_key_id", postgresql.UUID(), autoincrement=False, nullable=True))
    op.execute("UPDATE broadcast_message SET api_key_id=created_by_api_key_id")  # move data over
    op.drop_constraint("ck_broadcast_message_created_by_not_null", "broadcast_message")
