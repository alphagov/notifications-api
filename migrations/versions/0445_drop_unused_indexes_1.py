"""

Revision ID: 0445_drop_unused_indexes_1
Revises: 0444_user_features_email_column
Create Date: 2024-05-14 11:35:58.545277

"""

from alembic import op


revision = "0445_drop_unused_indexes_1"
down_revision = "0444_user_features_email_column"


def upgrade():
    with op.get_context().autocommit_block():
        # 1
        op.drop_index(
            "ix_inbound_sms_history_created_at",
            table_name="inbound_sms_history",
            postgresql_concurrently=True,
        )
        # 2
        op.drop_index(
            "ix_users_name",
            table_name="users",
            postgresql_concurrently=True,
        )
        # 3
        op.drop_index(
            "ix_services_history_created_by_id",  # can't remove index from model as this is based on services table
            table_name="services_history",
            postgresql_concurrently=True,
        )
        # 4
        op.drop_index(
            "ix_services_history_organisation_id",  # can't remove index from model as this is based on services table
            table_name="services_history",
            postgresql_concurrently=True,
        )
        # 5
        op.drop_index(
            "ix_daily_sorted_letter_file_name",
            table_name="daily_sorted_letter",
            postgresql_concurrently=True,
        )


def downgrade():
    with op.get_context().autocommit_block():
        # 1
        op.create_index(
            "ix_inbound_sms_history_created_at",
            "inbound_sms_history",
            ["created_at"],
            unique=False,
            postgresql_concurrently=True,
        )
        # 2
        op.create_index(
            "ix_users_name",
            "users",
            ["name"],
            unique=False,
            postgresql_concurrently=True,
        )
        # 3
        op.create_index(
            "ix_services_history_created_by_id",
            "services_history",
            ["created_by_id"],
            unique=False,
            postgresql_concurrently=True,
        )
        # 4
        op.create_index(
            "ix_services_history_organisation_id",
            "services_history",
            ["organisation_id"],
            unique=False,
            postgresql_concurrently=True,
        )
        # 5
        op.create_index(
            "ix_daily_sorted_letter_file_name",
            "daily_sorted_letter",
            ["file_name"],
            unique=False,
            postgresql_concurrently=True,
        )
