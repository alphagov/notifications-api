"""

Revision ID: 0390_require_rate_limit_value
Revises: 0389_split_rate_limits
Create Date: 2022-12-16 16:07:34.859641

"""

import sqlalchemy as sa
from alembic import op

revision = "0390_require_rate_limit_value"
down_revision = "0389_split_rate_limits"


def upgrade():
    op.execute(
        """
        UPDATE services
        SET
            letter_message_limit = 999999999,
            sms_message_limit = 999999999,
            email_message_limit = 999999999
        """
    )
    op.execute(
        """
        UPDATE services_history
        SET
            letter_message_limit = 999999999,
            sms_message_limit = 999999999,
            email_message_limit = 999999999
        """
    )
    op.alter_column("services", "letter_message_limit", existing_type=sa.BIGINT(), nullable=False)
    op.alter_column("services", "sms_message_limit", existing_type=sa.BIGINT(), nullable=False)
    op.alter_column("services", "email_message_limit", existing_type=sa.BIGINT(), nullable=False)
    op.alter_column("services_history", "letter_message_limit", existing_type=sa.BIGINT(), nullable=False)
    op.alter_column("services_history", "sms_message_limit", existing_type=sa.BIGINT(), nullable=False)
    op.alter_column("services_history", "email_message_limit", existing_type=sa.BIGINT(), nullable=False)


def downgrade():
    op.alter_column("services_history", "email_message_limit", existing_type=sa.BIGINT(), nullable=True)
    op.alter_column("services_history", "sms_message_limit", existing_type=sa.BIGINT(), nullable=True)
    op.alter_column("services_history", "letter_message_limit", existing_type=sa.BIGINT(), nullable=True)
    op.alter_column("services", "email_message_limit", existing_type=sa.BIGINT(), nullable=True)
    op.alter_column("services", "sms_message_limit", existing_type=sa.BIGINT(), nullable=True)
    op.alter_column("services", "letter_message_limit", existing_type=sa.BIGINT(), nullable=True)
