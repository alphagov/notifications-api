"""empty message

Revision ID: 0012_complete_provider_details
Revises: 0011_ad_provider_details
Create Date: 2016-05-05 09:18:26.926275

"""

# revision identifiers, used by Alembic.
revision = "0012_complete_provider_details"
down_revision = "0011_ad_provider_details"

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ENUM


def upgrade():
    op.alter_column("provider_rates", "provider_id", existing_type=postgresql.UUID(), nullable=False)
    op.drop_column("provider_rates", "provider")
    op.alter_column("provider_statistics", "provider_id", existing_type=postgresql.UUID(), nullable=False)
    op.drop_column("provider_statistics", "provider")
    op.execute("drop type providers")


def downgrade():
    provider_enum = ENUM("loadtesting", "firetext", "mmg", "ses", "twilio", name="providers", create_type=True)
    provider_enum.create(op.get_bind(), checkfirst=False)

    op.add_column("provider_statistics", sa.Column("provider", provider_enum, autoincrement=False, nullable=True))
    op.alter_column("provider_statistics", "provider_id", existing_type=postgresql.UUID(), nullable=True)
    op.add_column("provider_rates", sa.Column("provider", provider_enum, autoincrement=False, nullable=True))
    op.alter_column("provider_rates", "provider_id", existing_type=postgresql.UUID(), nullable=True)

    op.execute(
        "UPDATE provider_rates set provider = 'mmg' where provider_id = (select id from provider_details where identifier = 'mmg')"
    )
    op.execute(
        "UPDATE provider_rates set provider = 'firetext' where provider_id = (select id from provider_details where identifier = 'firetext')"
    )
    op.execute(
        "UPDATE provider_rates set provider = 'ses' where provider_id = (select id from provider_details where identifier = 'ses')"
    )
    op.execute(
        "UPDATE provider_rates set provider = 'loadtesting' where provider_id = (select id from provider_details where identifier = 'loadtesting')"
    )

    op.execute(
        "UPDATE provider_statistics set provider = 'mmg' where provider_id = (select id from provider_details where identifier = 'mmg')"
    )
    op.execute(
        "UPDATE provider_statistics set provider = 'firetext' where provider_id = (select id from provider_details where identifier = 'firetext')"
    )
    op.execute(
        "UPDATE provider_statistics set provider = 'ses' where provider_id = (select id from provider_details where identifier = 'ses')"
    )
    op.execute(
        "UPDATE provider_statistics set provider = 'loadtesting' where provider_id = (select id from provider_details where identifier = 'loadtesting')"
    )

    op.alter_column("provider_rates", "provider", existing_type=postgresql.UUID(), nullable=False)

    op.alter_column("provider_statistics", "provider", existing_type=postgresql.UUID(), nullable=False)
