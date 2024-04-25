"""

Revision ID: 0119_add_email_reply_to
Revises: 0118_service_sms_senders
Create Date: 2017-09-07 15:29:49.087143

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0119_add_email_reply_to"
down_revision = "0118_service_sms_senders"


def upgrade():
    op.create_table(
        "service_email_reply_to",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email_address", sa.Text(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_service_email_reply_to_service_id"), "service_email_reply_to", ["service_id"], unique=False
    )


def downgrade():
    op.drop_index(op.f("ix_service_email_reply_to_service_id"), table_name="service_email_reply_to")
    op.drop_table("service_email_reply_to")
