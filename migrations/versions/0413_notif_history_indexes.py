"""

Revision ID: 0413_notif_history_indexes
Revises: 0412_letter_despatch
Create Date: 2023-06-06 10:03:04.623630

"""
from alembic import op


revision = "0413_notif_history_indexes"
down_revision = "0412_letter_despatch"


def upgrade():
    with op.get_context().autocommit_block():
        op.create_index(
            op.f("ix_notification_history_created_at"),
            "notification_history",
            ["created_at"],
            unique=False,
            postgresql_concurrently=True,
        )
        op.create_index(
            op.f("ix_notification_history_notification_type"),
            "notification_history",
            ["notification_type"],
            unique=False,
            postgresql_concurrently=True,
        )


def downgrade():
    op.drop_index(op.f("ix_notification_history_notification_type"), table_name="notification_history")
    op.drop_index(op.f("ix_notification_history_created_at"), table_name="notification_history")
