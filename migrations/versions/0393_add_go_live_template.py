"""

Revision ID: 0393_add_go_live_template
Revises: 0392_go_live_cols_non_nullable
Create Date: 2022-12-28 12:12:12.929661

"""

import textwrap

from alembic import op
from flask import current_app

revision = "0393_add_go_live_template"
down_revision = "0392_go_live_cols_non_nullable"


template_id = "5c7cfc0f-c3f4-4bd6-9a84-5a144aad5425"
template_content = textwrap.dedent(
    """\
    Hi ((name))

    ((requester_name)) has requested for ‘((service_name))’ to be made live.

    # To approve or reject this request

    Review this request at: ((make_service_live_link))

    # If you have any questions

    To ask ((requester_name)) about their service reply to this email or contact them directly at ((requester_email_address))

    ***

    You are receiving this email because you are a team member of ((organisation_name)) on GOV.UK Notify.

    If you need help with this request or anything else, get in touch via our support page at ((support_page_link))

    Thanks,
    GOV.​UK Notify team

    https://www.gov.uk/notify
    """
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
                hidden
            )
            VALUES (
                '{template_id}',
                'Service wants to go live (for organisation users)',
                'email',
                current_timestamp,
                'Request to go live: ((service_name))',
                '{template_content}',
                false,
                '{current_app.config["NOTIFY_SERVICE_ID"]}',
                '{current_app.config["NOTIFY_USER_ID"]}',
                1,
                'normal',
                false
            )
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
        """
    )


def downgrade():
    for table, column_name in (
        ("notifications", "template_id"),
        ("notification_history", "template_id"),
        ("template_redacted", "template_id"),
        ("templates", "id"),
        ("templates_history", "id"),
    ):
        op.execute(f"DELETE FROM {table} WHERE {column_name} = '{template_id}'")
