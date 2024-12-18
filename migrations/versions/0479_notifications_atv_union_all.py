"""
Create Date: 2024-11-25 17:01:33.329568
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0479_notifications_atv_union_all"
down_revision = "0478_drop_contacted_users"


def upgrade():
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


def downgrade():
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
