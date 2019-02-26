"""

Revision ID: 0265_add_confirm_edit_templates
Revises: 0264_add_folder_permissions_perm
Create Date: 2019-02-26 15:16:53.268135

"""
from datetime import datetime

from alembic import op
from flask import current_app


revision = '0265_add_confirm_edit_templates'
down_revision = '0264_add_folder_permissions_perm'

email_template_id = "c73f1d71-4049-46d5-a647-d013bdeca3f0"
mobile_template_id = "8a31520f-4751-4789-8ea1-fe54496725eb"


def upgrade():
    template_insert = """
        INSERT INTO templates (id, name, template_type, created_at, content, archived, service_id, subject,
        created_by_id, version, process_type, hidden)
        VALUES ('{}', '{}', '{}', '{}', '{}', False, '{}', '{}', '{}', 1, '{}', false)
    """
    template_history_insert = """
        INSERT INTO templates_history (id, name, template_type, created_at, content, archived, service_id, subject,
        created_by_id, version, process_type, hidden)
        VALUES ('{}', '{}', '{}', '{}', '{}', False, '{}', '{}', '{}', 1, '{}', false)
    """

    email_template_content = '\n'.join([
        "Dear ((name)),",
        "",
        "((servicemanagername)) changed your Notify account email address to:",
        "",
        "((email address))",
        "",
        "You’ll need to use this email address next time you sign in.",
        "",
        "Thanks",
        "",
        "GOV.​UK Notify team",
        "https://www.gov.uk/notify"
    ])

    email_template_name = "Email address changed by service manager"
    email_template_subject = 'Your GOV.UK Notify email address has changed'

    op.execute(
        template_history_insert.format(
            email_template_id,
            email_template_name,
            'email',
            datetime.utcnow(),
            email_template_content,
            current_app.config['NOTIFY_SERVICE_ID'],
            email_template_subject,
            current_app.config['NOTIFY_USER_ID'],
            'normal'
        )
    )

    op.execute(
        template_insert.format(
            email_template_id,
            email_template_name,
            'email',
            datetime.utcnow(),
            email_template_content,
            current_app.config['NOTIFY_SERVICE_ID'],
            email_template_subject,
            current_app.config['NOTIFY_USER_ID'],
            'normal'
        )
    )

    mobile_template_content = """Your mobile number was changed by ((servicemanagername)). Next time you sign in, your Notify authentication code will be sent to this phone."""

    mobile_template_name = "Phone number changed by service manager"

    op.execute(
        template_history_insert.format(
            mobile_template_id,
            mobile_template_name,
            'sms',
            datetime.utcnow(),
            mobile_template_content,
            current_app.config['NOTIFY_SERVICE_ID'],
            None,
            current_app.config['NOTIFY_USER_ID'],
            'normal'
        )
    )

    op.execute(
        template_insert.format(
            mobile_template_id,
            mobile_template_name,
            'sms',
            datetime.utcnow(),
            mobile_template_content,
            current_app.config['NOTIFY_SERVICE_ID'],
            None,
            current_app.config['NOTIFY_USER_ID'],
            'normal'
        )
    )


def downgrade():
    op.execute("DELETE FROM templates_history WHERE id = '{}'".format(email_template_id))
    op.execute("DELETE FROM templates WHERE id = '{}'".format(email_template_id))

    op.execute("DELETE FROM templates_history WHERE id = '{}'".format(mobile_template_id))
    op.execute("DELETE FROM templates WHERE id = '{}'".format(mobile_template_id))
