"""

Revision ID: 0373_add_notifications_view
Revises: 0372_remove_provider_rates
Create Date: 2022-05-18 09:39:45.260951

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0373_add_notifications_view'
down_revision = '0372_remove_provider_rates'


def upgrade():
    op.execute("""
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
    """)


def downgrade():
    op.execute("DROP VIEW notifications_all_time_view")
