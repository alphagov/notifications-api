"""

Revision ID: 0167_add_org_invite_template
Revises: 0166_add_org_user_stuff
Create Date: 2018-02-16 14:16:43.618062

"""
from datetime import datetime

from alembic import op
from flask import current_app


revision = '0167_add_org_invite_template'
down_revision = '0166_add_org_user_stuff'


template_id = '203566f0-d835-47c5-aa06-932439c86573'


def upgrade():
    template_insert = """
        INSERT INTO templates (id, name, template_type, created_at, content, archived, service_id, subject, created_by_id, version, process_type)
        VALUES ('{}', '{}', '{}', '{}', '{}', False, '{}', '{}', '{}', 1, '{}')
    """
    template_history_insert = """
        INSERT INTO templates_history (id, name, template_type, created_at, content, archived, service_id, subject, created_by_id, version, process_type)
        VALUES ('{}', '{}', '{}', '{}', '{}', False, '{}', '{}', '{}', 1, '{}')
    """

    template_content = '\n'.join([
        "((user_name)) has invited you to collaborate on ((organisation_name)) on GOV.UK Notify.",
        "",
        "GOV.UK Notify makes it easy to keep people updated by helping you send text messages, emails and letters.",
        "",
        "Open this link to create an account on GOV.UK Notify:",
        "((url))",
        "",
        "This invitation will stop working at midnight tomorrow. This is to keep ((organisation_name)) secure.",
    ])

    template_name = "Notify organisation invitation email"
    template_subject = '((user_name)) has invited you to collaborate on ((organisation_name)) on GOV.UK Notify'

    op.execute(
        template_history_insert.format(
            template_id,
            template_name,
            'email',
            datetime.utcnow(),
            template_content,
            current_app.config['NOTIFY_SERVICE_ID'],
            template_subject,
            current_app.config['NOTIFY_USER_ID'],
            'normal'
        )
    )

    op.execute(
        template_insert.format(
            template_id,
            template_name,
            'email',
            datetime.utcnow(),
            template_content,
            current_app.config['NOTIFY_SERVICE_ID'],
            template_subject,
            current_app.config['NOTIFY_USER_ID'],
            'normal'
        )
    )

    # clean up constraints on org_to_service - service_id-org_id constraint is redundant
    op.drop_constraint('organisation_to_service_service_id_organisation_id_key', 'organisation_to_service', type_='unique')


def downgrade():
    op.execute("DELETE FROM templates_history WHERE id = '{}'".format(template_id))
    op.execute("DELETE FROM templates WHERE id = '{}'".format(template_id))
    op.create_unique_constraint('organisation_to_service_service_id_organisation_id_key', 'organisation_to_service', ['service_id', 'organisation_id'])
