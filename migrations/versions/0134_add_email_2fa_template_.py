"""

Revision ID: 0134_add_email_2fa_template
Revises: 0133_set_services_sms_prefix
Create Date: 2017-11-03 13:52:59.715203

"""
from datetime import datetime

from alembic import op
from flask import current_app


revision = '0134_add_email_2fa_template'
down_revision = '0133_set_services_sms_prefix'

template_id = '299726d2-dba6-42b8-8209-30e1d66ea164'


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
        'Hi ((name)),',
        '',
        'To sign in to GOV.​UK Notify please open this link:',
        '((url))',
    ])

    template_name = "Notify email verify code"
    template_subject = 'Sign in to GOV.UK Notify'

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


def downgrade():
   op.execute("DELETE FROM templates_history WHERE id = '{}'".format(template_id))
   op.execute("DELETE FROM templates WHERE id = '{}'".format(template_id))
