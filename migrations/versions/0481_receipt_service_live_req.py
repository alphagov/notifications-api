"""

Revision ID: 0481_receipt_service_live_req
Revises: 0480_ntfcns_cpst_idx_nostatus
Create Date: 2024-12-02 17:34:15.732756

"""

import textwrap

from alembic import op
from flask import current_app

revision = "0481_receipt_service_live_req"
down_revision = "0480_ntfcns_cpst_idx_nostatus"


template_id = "c7083bfe-1b9a-4ff9-bd5c-30508727df6e"
template_content = textwrap.dedent(
    """\
    Hi ((name))

    You have sent a request to go live for a GOV.​UK Notify service called ‘((service_name))’.

    Your request was sent to the following members of ((organisation_name)):

    ((organisation_team_member_names)) 

    If you do not receive an update about your request in the next 2 working days, please reply to this email and let us know.

    Thanks

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
                hidden,
                has_unsubscribe_link
            )
            VALUES (
                '{template_id}',
                'Receipt email after requesting to go live (self-approval)',
                'email',
                current_timestamp,
                'Your request to go live',
                '{template_content}',
                false,
                '{current_app.config["NOTIFY_SERVICE_ID"]}',
                '{current_app.config["NOTIFY_USER_ID"]}',
                1,
                'normal',
                false,
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
