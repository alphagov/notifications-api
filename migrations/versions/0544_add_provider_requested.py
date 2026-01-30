"""
Create Date: 2025-02-26 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0544_add_provider_requested"
down_revision = "0543_letter_rates_from_5_01_26"


def upgrade():
    op.add_column("jobs", sa.Column("provider_requested", sa.String(), nullable=True))
    op.add_column("notifications", sa.Column("provider_requested", sa.String(), nullable=True))
    op.add_column("notification_history", sa.Column("provider_requested", sa.String(), nullable=True))

    op.execute(
        """
        CREATE OR REPLACE VIEW notifications_all_time_view AS
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
                document_download_count,
                provider_requested
            FROM notifications
        ) UNION ALL
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
                document_download_count,
                provider_requested
            FROM notification_history
        )
    """
    )


def downgrade():
    op.execute("DROP VIEW IF EXISTS notifications_all_time_view")
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
        ) UNION ALL
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

    op.drop_column("notification_history", "provider_requested")
    op.drop_column("notifications", "provider_requested")
    op.drop_column("jobs", "provider_requested")
