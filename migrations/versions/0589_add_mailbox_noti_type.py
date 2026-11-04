"""
Create Date: 2026-11-03 10:19:17.905462
"""

from alembic import op
import sqlalchemy as sa

revision = '0589_add_mailbox_noti_type'
down_revision = '0588_active_letter_branding'


def upgrade():
    op.execute("ALTER TYPE notification_type ADD VALUE 'mailbox'")


def downgrade():
    """
    For use in a proof of concept only, a downgrade like this would cause issues if run in production
    """
    enum_name = "notification_type"
    tmp_name = "tmp_" + enum_name

    original_values = ("email", "sms", "letter")
    original_type = sa.Enum(*original_values, name=enum_name)

    # Delete any existing data that has "mailbox" type
    op.execute("DELETE FROM notifications WHERE notification_type = 'mailbox'")
    op.execute("DELETE FROM notification_history WHERE notification_type = 'mailbox'")
    op.execute("DELETE FROM provider_details WHERE notification_type = 'mailbox'")
    op.execute("DELETE FROM provider_details_history WHERE notification_type = 'mailbox'")
    op.execute("DELETE FROM default_annual_allowance WHERE notification_type = 'mailbox'")
    op.execute("DELETE FROM rates WHERE notification_type = 'mailbox'")
    op.execute("DELETE FROM service_data_retention WHERE notification_type = 'mailbox'")

    # Delete the view and constraint that won't automatically update when the enum is renamed
    op.execute("DROP VIEW notifications_all_time_view")
    op.execute("ALTER TABLE notifications DROP CONSTRAINT ck_unsubscribe_link_is_null_if_notification_not_an_email")

    # Rename the current enum and create the original enum we want to use
    op.execute(f"ALTER TYPE {enum_name} RENAME TO {tmp_name}")
    original_type.create(op.get_bind())

    # Change the columns that use the enum to use the original one
    op.execute(f"ALTER TABLE notifications ALTER COLUMN notification_type TYPE {enum_name} USING notification_type::text::{enum_name}")
    op.execute(f"ALTER TABLE notification_history ALTER COLUMN notification_type TYPE {enum_name} USING notification_type::text::{enum_name}")
    op.execute(f"ALTER TABLE provider_details ALTER COLUMN notification_type TYPE {enum_name} USING notification_type::text::{enum_name}")
    op.execute(f"ALTER TABLE provider_details_history ALTER COLUMN notification_type TYPE {enum_name} USING notification_type::text::{enum_name}")
    op.execute(f"ALTER TABLE default_annual_allowance ALTER COLUMN notification_type TYPE {enum_name} USING notification_type::text::{enum_name}")
    op.execute(f"ALTER TABLE rates ALTER COLUMN notification_type TYPE {enum_name} USING notification_type::text::{enum_name}")
    op.execute(f"ALTER TABLE service_data_retention ALTER COLUMN notification_type TYPE {enum_name} USING notification_type::text::{enum_name}")

    # Recreate the check constraint and view
    op.create_check_constraint(
        "ck_unsubscribe_link_is_null_if_notification_not_an_email",
        "notifications",
        """
        notification_type = 'email' OR unsubscribe_link is null
        """,
    )

    op.execute(
        """
        CREATE VIEW notifications_all_time_view AS
        (
            SELECT
                id,
                job_id,
                job_row_number,
                service_id,
                template_id,
                template_version,
                api_key_id,
                key_type,
                billable_units,
                notification_type,
                created_at,
                sent_at,
                sent_by,
                updated_at,
                notification_status,
                reference,
                client_reference,
                international,
                phone_prefix,
                rate_multiplier,
                created_by_id,
                postage,
                document_download_count
            FROM notifications
        ) UNION
        (
            SELECT
                id,
                job_id,
                job_row_number,
                service_id,
                template_id,
                template_version,
                api_key_id,
                key_type,
                billable_units,
                notification_type,
                created_at,
                sent_at,
                sent_by,
                updated_at,
                notification_status,
                reference,
                client_reference,
                international,
                phone_prefix,
                rate_multiplier,
                created_by_id,
                postage,
                document_download_count
            FROM notification_history
        )
    """
    )

    # Delete the enum that contained "mailbox"
    op.execute(f"DROP TYPE {tmp_name}")
