"""

Revision ID: 0421_notification_event_log
Revises: 0420_unique_service_name_1
Create Date: 2023-01-04 14:14:19.133958

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0421_notification_event_log"
down_revision = "0420_unique_service_name_1"


def upgrade():
    op.create_table(
        "notification_event_log",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("notification_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("happened_at", sa.DateTime(), nullable=True),
        sa.Column("notification_status", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["notification_status"],
            ["notification_status_types.name"],
        ),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_notification_event_log_notification_id"), "notification_event_log", ["notification_id"], unique=False
    )


def downgrade():
    op.drop_index(op.f("ix_notification_event_log_notification_id"), table_name="notification_event_log")
    op.drop_table("notification_event_log")
