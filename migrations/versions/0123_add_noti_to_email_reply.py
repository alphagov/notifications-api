"""

Revision ID: 0123_add_noti_to_email_reply
Revises: 0122_add_service_letter_contact
Create Date: 2017-09-27 09:42:39.412731

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0123_add_noti_to_email_reply"
down_revision = "0122_add_service_letter_contact"


def upgrade():
    op.create_table(
        "notification_to_email_reply_to",
        sa.Column("notification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_email_reply_to_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["notification_id"],
            ["notifications.id"],
        ),
        sa.ForeignKeyConstraint(
            ["service_email_reply_to_id"],
            ["service_email_reply_to.id"],
        ),
        sa.PrimaryKeyConstraint("notification_id", "service_email_reply_to_id"),
    )
    op.create_index(
        op.f("ix_notification_to_email_reply_to_notification_id"),
        "notification_to_email_reply_to",
        ["notification_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_notification_to_email_reply_to_service_email_reply_to_id"),
        "notification_to_email_reply_to",
        ["service_email_reply_to_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_notification_to_email_reply_to_service_email_reply_to_id"), table_name="notification_to_email_reply_to"
    )
    op.drop_index(
        op.f("ix_notification_to_email_reply_to_notification_id"), table_name="notification_to_email_reply_to"
    )
    op.drop_table("notification_to_email_reply_to")
