"""
Create Date: 2025-12-16 07:30:56.228804
"""

from alembic import op

revision = '0542_backfill_confirm_sender'
down_revision = '0541_service_confirm_sender_name'


def upgrade():
    op.execute(
        "UPDATE services SET confirmed_email_sender_name = true "
        "WHERE custom_email_sender_name IS NOT NULL and confirmed_email_sender_name IS NULL"
    )
    op.execute(
        "UPDATE services_history SET confirmed_email_sender_name = true "
        "WHERE custom_email_sender_name IS NOT NULL and confirmed_email_sender_name IS NULL"
    )


def downgrade():
    """
    There's not a nice way to only reverse the changes for services that were changed in the upgrade -
    this will also affect services which have had the confirmed_email_sender_name column populated since the
    migration ran. That won't have any serious effects for services - it may just mean they need to confirm that
    they are happy with the sender name again.
    """
    op.execute(
        "UPDATE services SET confirmed_email_sender_name = NULL "
        "WHERE custom_email_sender_name IS NOT NULL and confirmed_email_sender_name = true"
    )
    op.execute(
        "UPDATE services_history SET confirmed_email_sender_name = NULL "
        "WHERE custom_email_sender_name IS NOT NULL and confirmed_email_sender_name = true"
    )
