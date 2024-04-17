"""

Revision ID: 0389_split_rate_limits
Revises: 0388_populate_letter_branding
Create Date: 2022-12-11 08:01:58.001061

"""

import sqlalchemy as sa
from alembic import op

revision = "0389_split_rate_limits"
down_revision = "0388_populate_letter_branding"


def upgrade():
    op.add_column("services", sa.Column("letter_message_limit", sa.BigInteger(), nullable=True))
    op.add_column("services", sa.Column("sms_message_limit", sa.BigInteger(), nullable=True))
    op.add_column("services", sa.Column("email_message_limit", sa.BigInteger(), nullable=True))
    op.add_column("services_history", sa.Column("letter_message_limit", sa.BigInteger(), nullable=True))
    op.add_column("services_history", sa.Column("sms_message_limit", sa.BigInteger(), nullable=True))
    op.add_column("services_history", sa.Column("email_message_limit", sa.BigInteger(), nullable=True))


def downgrade():
    op.drop_column("services_history", "email_message_limit")
    op.drop_column("services_history", "sms_message_limit")
    op.drop_column("services_history", "letter_message_limit")
    op.drop_column("services", "email_message_limit")
    op.drop_column("services", "sms_message_limit")
    op.drop_column("services", "letter_message_limit")
