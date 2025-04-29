"""
Create Date: 2025-04-29 12:36:49.360512
"""

import textwrap

from alembic import op
from flask import current_app
from sqlalchemy import text

revision = '0500_update_intl_limit_values'
down_revision = '0499_merge_callback_tables'


def upgrade():
    conn = op.get_bind()

    # First get services that sent international SMS in the last 12 months, and how many they sent on their busiest day.
    # Then for each of those services, if they sent more than 50 on their busiest day,
    #  set their new international_sms_message_limit to busiest day * 2.

    # Then get all remaining services that have their international_sms_message_limit set to default value (250,000)
    # and set their limit to 100 per day.

    services_with_intl_sms = conn.execute(
        text(
            textwrap.dedent(
                """
                SELECT intl_billing.service_id, MAX(intl_billing.intl_sent) AS max_daily_intl
                FROM (SELECT
                    service_id, bst_date, SUM(notifications_sent) as intl_sent FROM ft_billing WHERE bst_date > '2024-04-21' AND notification_type = 'sms' AND international = true GROUP BY service_id, bst_date
                ) AS intl_billing

                GROUP BY intl_billing.service_id ORDER BY max_daily_intl DESC;
                """
            )
        ),
    ).fetchall()

    services_with_custom_limit = []

    for service_id, max_daily_intl in services_with_intl_sms:
        new_limit = max_daily_intl * 2 if max_daily_intl > 50 else 100
        services_with_custom_limit.append({"service_id": service_id, "new_limit": new_limit})

    print(f"Updating {len(services_with_custom_limit)} services.")
    if services_with_custom_limit:
        conn.execute(
            text(
                textwrap.dedent(
                    """
                    UPDATE services
                    SET
                        international_sms_message_limit = :new_limit,
                        updated_at = now()
                    WHERE
                        international_sms_message_limit = 250000 AND
                        id = :service_id
                    """
                )
            ),
            services_with_custom_limit,
        )

    print(f"Updating remaining services.")
    conn.execute(
        text(
            textwrap.dedent(
                """
                UPDATE services
                SET
                    international_sms_message_limit = 100,
                    updated_at = now()
                WHERE
                    international_sms_message_limit = 250000
                """
            )
        ),
        services_with_custom_limit,
    )


def downgrade():
    pass
