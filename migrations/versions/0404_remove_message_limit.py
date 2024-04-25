"""

Revision ID: 0404_remove_message_limit
Revises: 0403_letter_rates_jan_2023
Create Date: 2023-01-27 11:14:29.038116

"""

import sqlalchemy as sa
from alembic import op

revision = "0404_remove_message_limit"
down_revision = "0403_letter_rates_jan_2023"


def upgrade():
    op.drop_column("services", "message_limit")
    op.drop_column("services_history", "message_limit")


def downgrade():
    op.add_column("services_history", sa.Column("message_limit", sa.BIGINT(), autoincrement=False, nullable=True))
    op.add_column("services", sa.Column("message_limit", sa.BIGINT(), autoincrement=False, nullable=True))
