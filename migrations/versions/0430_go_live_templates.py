"""

Revision ID: 0430_go_live_templates
Revises: 0429_add_new_email_sender_fields
Create Date: 2023-10-31 13:23:51.260909

"""

import textwrap

from alembic import op
from flask import current_app

revision = "0430_go_live_templates"
down_revision = "0429_add_new_email_sender_fields"

continue_template_id = "62f12a62-742b-4458-9336-741521b131c7"
continue_template_content = textwrap.dedent(
    """
    ((body))
    """
)

reject_template_id = "507d0796-9e23-4ad7-b83b-5efbd9496866"
reject_template_content = textwrap.dedent(
    """
Hi ((name))

# Your request to go live was rejected

You sent a request to go live for a GOV.UK Notify service called ‘((service_name))’.

((organisation_team_member_name)) at ((organisation_name)) rejected the request for the following reason:

((reason))

If you have any questions, you can email ((organisation_team_member_name)) at ((organisation_team_member_email))

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
                '{continue_template_id}',
                'Reminder: continue self-service go live journey (for organisation users)',
                'email',
                current_timestamp,
                'Request to go live: ((service_name))',
                '{continue_template_content}',
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
            '{continue_template_id}',
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
                '{reject_template_id}',
                'Reject self-service go live request',
                'email',
                current_timestamp,
                'Your request to go live has been rejected',
                '{reject_template_content}',
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
            '{reject_template_id}',
            false,
            current_timestamp,
            '{current_app.config["NOTIFY_USER_ID"]}'
        )
        ON CONFLICT DO NOTHING
        """
    )


def downgrade():
    # I don't consider there to be a safe downgrade path as other tables could theoretically have FK dependencies
    # on the inserted templates (eg notifications). I don't like the idea of deleting the record of notifications
    # in order to be able to drop the templates.
    pass
