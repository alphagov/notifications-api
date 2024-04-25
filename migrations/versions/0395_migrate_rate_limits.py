"""

Revision ID: 0395_migrate_rate_limits
Revises: 0394_letter_branding_cols
Create Date: 2023-01-06 09:27:38.125105

"""

from alembic import op

revision = "0395_migrate_rate_limits"
down_revision = "0394_letter_branding_cols"


def upgrade():
    op.execute(
        """
        UPDATE services
        SET email_message_limit = (
            CASE
                WHEN restricted = FALSE THEN
                    message_limit
                ELSE
                    50
            END
        )
        WHERE email_message_limit = 999999999
        """
    )
    op.execute(
        """
        UPDATE services
        SET sms_message_limit = (
            CASE
                WHEN restricted = FALSE THEN
                    message_limit
                ELSE
                    50
            END
        )
        WHERE sms_message_limit = 999999999
        """
    )
    op.execute(
        """
        UPDATE services
        SET letter_message_limit = (
            CASE
                WHEN restricted = FALSE THEN
                    20000
                ELSE
                    50
            END
        )
        WHERE letter_message_limit = 999999999
        """
    )

    # Set this extremely high, but retaining the message limit for the case where we want to downgrade.
    op.execute(
        """
        UPDATE services
        SET message_limit = 1000000000 + message_limit
        """
    )


def downgrade():
    # Recover the original message limit and apply it - so we can also downgrade the per-channel limits correctly.
    op.execute(
        """
        UPDATE services
        SET message_limit = message_limit - 1000000000
        """
    )

    op.execute(
        """
        UPDATE services
        SET email_message_limit = 999999999
        WHERE email_message_limit = message_limit OR email_message_limit = 50
        """
    )
    op.execute(
        """
        UPDATE services
        SET sms_message_limit = 999999999
        WHERE sms_message_limit = message_limit OR sms_message_limit = 50
        """
    )
    op.execute(
        """
        UPDATE services
        SET letter_message_limit = 999999999
        WHERE letter_message_limit = 20000 OR letter_message_limit = 50
        """
    )
