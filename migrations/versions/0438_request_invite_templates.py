"""

Revision ID: 0438_request_invite_templates
Revises: 0437_min_numeric_scl_aux_tbls
Create Date: 2023-12-11 16:21:05.947886

"""
import textwrap
from alembic import op
from flask import current_app


revision = "0438_request_invite_templates"
down_revision = "0437_min_numeric_scl_aux_tbls"


request_invite_to_a_service_template_id = "77677459-f862-44ee-96d9-b8cb2323d407"
request_invite_to_a_service_template_content = textwrap.dedent(
    """\
Hi ((name))

((requester_name)) would like to join the ‘((service_name))’ team on GOV.UK Notify.

((reason_given??They gave the following reason for wanting to join:))

((reason))

Use this link to invite ((requester_name)) to join the team:

((url))

If you have any questions, you can email ((requester_name)) at ((requester_email))

Thanks

GOV.​UK Notify team
https://www.gov.uk/notify
    """
)


receipt_for_request_invite_to_a_service_template_id = "38bcd263-6ce8-431f-979d-8e637c1f0576"
receipt_for_request_invite_to_a_service_template_content = textwrap.dedent(
    """\
    Hi ((name))

    …

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
                hidden
            )
            VALUES (
                '{request_invite_to_a_service_template_id}',
                'Request invite to a service',
                'email',
                current_timestamp,
                '((requester_name)) wants to join your GOV.UK Notify service',
                '{request_invite_to_a_service_template_content}',
                false,
                '{current_app.config["NOTIFY_SERVICE_ID"]}',
                '{current_app.config["NOTIFY_USER_ID"]}',
                1,
                'normal',
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
            '{request_invite_to_a_service_template_id}',
            false,
            current_timestamp,
            '{current_app.config["NOTIFY_USER_ID"]}'
        )
        ON CONFLICT DO NOTHING
        """
    )

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
                '{receipt_for_request_invite_to_a_service_template_id}',
                'Receipt email after requesting service invite',
                'email',
                current_timestamp,
                '',
                '{receipt_for_request_invite_to_a_service_template_content}',
                false,
                '{current_app.config["NOTIFY_SERVICE_ID"]}',
                '{current_app.config["NOTIFY_USER_ID"]}',
                1,
                'normal',
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
            '{receipt_for_request_invite_to_a_service_template_id}',
            false,
            current_timestamp,
            '{current_app.config["NOTIFY_USER_ID"]}'
        )
        ON CONFLICT DO NOTHING
        """
    )


def downgrade():
    pass
