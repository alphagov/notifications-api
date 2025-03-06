"""
Create Date: 2024-08-20 18:50:23.266628
"""

import textwrap
from alembic import op
from flask import current_app


revision = "0461_user_research_email"
down_revision = "0460_letter_rates_july_2024"


template_id = "55bcb671-4924-46c5-a00d-1a9d48458008"
template_content = textwrap.dedent(
    """
Hi ((name))
# How easy was it to start using GOV.UK Notify?

Please take 30 seconds to let us know:

https://surveys.publishing.service.gov.uk/s/notify-getting-started/

If you want to, you can tell us more about your experiences so far – from creating an account to setting up your first service.

We’ll read every piece of feedback we get, and your insights will help us to make GOV.UK Notify better for everyone.

Kind regards
GOV.UK Notify

---

If you do not want to take part in user research, you can [unsubscribe from these emails](https://www.notifications.service.gov.uk/your-account/take-part-in-user-research).    """
)


def upgrade():
    for table_name in ("templates", "templates_history"):
        op.execute(
            f"""
            INSERT INTO {table_name} (
                id,
                name,
                template_type,
                created_at,
                subject,
                content,
                archived,
                service_id,
                created_by_id,
                version,
                process_type,
                hidden,
                has_unsubscribe_link
            )
            VALUES (
                '{template_id}',
                'New user survey',
                'email',
                current_timestamp,
                'How easy was it to start using GOV.UK Notify?',
                '{template_content}',
                false,
                '{current_app.config["NOTIFY_SERVICE_ID"]}',
                '{current_app.config["NOTIFY_USER_ID"]}',
                1,
                'normal',
                false,
                false
            )
            ON CONFLICT DO NOTHING
            """
        )

    op.execute(
        f"""
        INSERT INTO template_redacted
        (
            template_id,
            redact_personalisation,
            updated_at,
            updated_by_id
        ) VALUES (
            '{template_id}',
            false,
            current_timestamp,
            '{current_app.config["NOTIFY_USER_ID"]}'
        )
        ON CONFLICT DO NOTHING
        """
    )


def downgrade():
    pass
