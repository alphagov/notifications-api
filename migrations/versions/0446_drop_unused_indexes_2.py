"""

Revision ID: 0446_drop_unused_indexes_2
Revises: 0445_drop_unused_indexes_1
Create Date: 2023-09-17 15:17:58.545277

"""

from alembic import op


revision = "0446_drop_unused_indexes_2"
down_revision = "0445_drop_unused_indexes_1"


def upgrade():
    with op.get_context().autocommit_block():
        # 6
        op.drop_index(
            "ix_users_auth_type",
            table_name="users",
            postgresql_concurrently=True,
        )
        # 7
        op.drop_index(
            "ix_api_keys_history_created_by_id",  # can't remove index from model as this is based on api_keys table
            table_name="api_keys_history",
            postgresql_concurrently=True,
        )
        # 8
        op.drop_index(
            "ix_api_keys_history_key_type",
            table_name="api_keys_history",
            postgresql_concurrently=True,
        )
        # 9
        op.drop_index(
            "ix_api_keys_key_type",
            table_name="api_keys",
            postgresql_concurrently=True,
        )


def downgrade():
    with op.get_context().autocommit_block():
        # 6
        op.create_index(
            "ix_users_auth_type",
            "users",
            ["auth_type"],
            unique=False,
            postgresql_concurrently=True,
        )
        # 7
        op.create_index(
            "ix_api_keys_history_created_by_id",
            "api_keys_history",
            ["created_by_id"],
            unique=False,
            postgresql_concurrently=True,
        )
        # 8
        op.create_index(
            "ix_api_keys_history_key_type",
            "api_keys_history",
            ["key_type"],
            unique=False,
            postgresql_concurrently=True,
        )
        # 9
        op.create_index(
            "ix_api_keys_key_type",
            "api_keys",
            ["key_type"],
            unique=False,
            postgresql_concurrently=True,
        )
