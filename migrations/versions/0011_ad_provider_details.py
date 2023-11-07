"""empty message

Revision ID: 0011_ad_provider_details
Revises: 0010_events_table
Create Date: 2016-05-05 09:14:29.328841

"""

# revision identifiers, used by Alembic.
revision = "0011_ad_provider_details"
down_revision = "0010_events_table"

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


def upgrade():
    op.create_table(
        "provider_details",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("identifier", sa.String(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("notification_type", sa.Enum("email", "sms", "letter", name="notification_type"), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.add_column("provider_rates", sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(op.f("ix_provider_rates_provider_id"), "provider_rates", ["provider_id"], unique=False)
    op.create_foreign_key("provider_rate_to_provider_fk", "provider_rates", "provider_details", ["provider_id"], ["id"])
    op.add_column("provider_statistics", sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(op.f("ix_provider_statistics_provider_id"), "provider_statistics", ["provider_id"], unique=False)
    op.create_foreign_key(
        "provider_stats_to_provider_fk", "provider_statistics", "provider_details", ["provider_id"], ["id"]
    )

    op.execute(
        "INSERT INTO provider_details (id, display_name, identifier, priority, notification_type, active) values ('{}', 'MMG', 'mmg', 10, 'sms', true)".format(
            str(uuid.uuid4())
        )
    )
    op.execute(
        "INSERT INTO provider_details (id, display_name, identifier, priority, notification_type, active) values ('{}', 'Firetext', 'firetext', 20, 'sms', true)".format(
            str(uuid.uuid4())
        )
    )
    op.execute(
        "INSERT INTO provider_details (id, display_name, identifier, priority, notification_type, active) values ('{}', 'AWS SES', 'ses', 10, 'email', true)".format(
            str(uuid.uuid4())
        )
    )
    op.execute(
        "UPDATE provider_rates set provider_id = (select id from provider_details where identifier = 'mmg') where provider = 'mmg'"
    )
    op.execute(
        "UPDATE provider_rates set provider_id = (select id from provider_details where identifier = 'firetext') where provider = 'firetext'"
    )
    op.execute(
        "UPDATE provider_rates set provider_id = (select id from provider_details where identifier = 'ses') where provider = 'ses'"
    )
    op.execute(
        "UPDATE provider_statistics set provider_id = (select id from provider_details where identifier = 'mmg') where provider = 'mmg'"
    )
    op.execute(
        "UPDATE provider_statistics set provider_id = (select id from provider_details where identifier = 'firetext') where provider = 'firetext'"
    )
    op.execute(
        "UPDATE provider_statistics set provider_id = (select id from provider_details where identifier = 'ses') where provider = 'ses'"
    )


def downgrade():
    op.drop_index(op.f("ix_provider_statistics_provider_id"), table_name="provider_statistics")
    op.drop_column("provider_statistics", "provider_id")
    op.drop_index(op.f("ix_provider_rates_provider_id"), table_name="provider_rates")
    op.drop_column("provider_rates", "provider_id")

    op.drop_table("provider_details")
    op.execute("drop type notification_type")
