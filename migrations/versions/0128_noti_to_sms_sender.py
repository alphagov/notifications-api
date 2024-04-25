"""

Revision ID: 0128_noti_to_sms_sender
Revises: 0127_remove_unique_constraint
Create Date: 2017-10-26 15:17:00.752706

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0128_noti_to_sms_sender"
down_revision = "0127_remove_unique_constraint"


def upgrade():
    op.create_index(
        op.f("ix_service_letter_contacts_service_id"), "service_letter_contacts", ["service_id"], unique=False
    )
    op.drop_index("ix_service_letter_contact_service_id", table_name="service_letter_contacts")
    op.create_index(op.f("ix_service_sms_senders_service_id"), "service_sms_senders", ["service_id"], unique=False)
    op.execute(
        "ALTER TABLE templates_history ALTER COLUMN template_type TYPE template_type USING template_type::template_type"
    )

    # new table
    op.create_table(
        "notification_to_sms_sender",
        sa.Column("notification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_sms_sender_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["notification_id"],
            ["notifications.id"],
        ),
        sa.ForeignKeyConstraint(
            ["service_sms_sender_id"],
            ["service_sms_senders.id"],
        ),
        sa.PrimaryKeyConstraint("notification_id", "service_sms_sender_id"),
    )
    op.create_index(
        op.f("ix_notification_to_sms_sender_notification_id"),
        "notification_to_sms_sender",
        ["notification_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_notification_to_sms_sender_service_sms_sender_id"),
        "notification_to_sms_sender",
        ["service_sms_sender_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_service_sms_senders_service_id"), table_name="service_sms_senders")
    op.create_index("ix_service_letter_contact_service_id", "service_letter_contacts", ["service_id"], unique=False)
    op.drop_index(op.f("ix_service_letter_contacts_service_id"), table_name="service_letter_contacts")
    op.alter_column("templates_history", "template_type", type_=sa.VARCHAR(), existing_nullable=False)

    op.drop_table("notification_to_sms_sender")
