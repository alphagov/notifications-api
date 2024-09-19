"""
Create Date: 2024-09-11 11:50:23.266628
"""

import textwrap
from alembic import op
from flask import current_app


revision = "0465_requester_invite_approved"
down_revision = "0464_create_svc_join_requests"

template_id = "4d8ee728-100e-4f0e-8793-5638cfa4ffa4"
template_content = textwrap.dedent(
    """
Hi ((requester name))

((approver name)) has approved your request to join the following GOV.UK Notify service:

^[((service name))](((dashboard url)))

Sign in to GOV.UK Notify to get started.

Thanks

GOV.​UK Notify
https://www.gov.uk/notify"""
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
                '03 - Requester - Your request has been approved',
                'email',
                current_timestamp,
                '((approver name)) has approved your request',
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
