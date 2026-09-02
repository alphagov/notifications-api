"""empty message

Revision ID: 0082_add_go_live_template
Revises: 0081_noti_status_as_enum
Create Date: 2017-05-10 16:06:04.070874

"""

# revision identifiers, used by Alembic.
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from flask import current_app

revision = "0082_add_go_live_template"
down_revision = "0081_noti_status_as_enum"

template_id = "618185c6-3636-49cd-b7d2-6f6f5eb3bdde"


def upgrade():
    template_insert = """
        INSERT INTO templates (id, name, template_type, created_at, content, archived, service_id, subject, created_by_id, version, process_type)
        VALUES ('{}', '{}', '{}', '{}', '{}', False, '{}', '{}', '{}', 1, '{}')
    """
    template_history_insert = """
        INSERT INTO templates_history (id, name, template_type, created_at, content, archived, service_id, subject, created_by_id, version, process_type)
        VALUES ('{}', '{}', '{}', '{}', '{}', False, '{}', '{}', '{}', 1, '{}')
    """

    template_content = """Hi ((name))

# Your GOV.UK Notify service is live

^ Service name: ((service name))

[Sign in to Notify](https://www.notifications.service.gov.uk/sign-in) to start sending messages.

## If you use our API

Create a live API key so you can send messages to anyone.

[See our API documentation for instructions](https://www.notifications.service.gov.uk/using-notify/api-documentation)

# Help and support

## If your sign-in details change

Ask a member of your service with the ‘manage settings, team and usage’ permission to update your email address or phone number.

## If you get stuck

Read our [guidance pages](https://www.notifications.service.gov.uk/using-notify).

If you cannot find the answer there, [contact support](https://www.notifications.service.gov.uk/support).

## If you see an error message

First, check the [status page](https://status.notifications.service.gov.uk/).

If your problem is not listed there, [contact support](https://www.notifications.service.gov.uk/support).

---

Thanks

GOV.​UK Notify
https://www.gov.uk/notify
"""

    template_name = "Automated \"You''re now live\" message"
    template_subject = "Your GOV.UK Notify service is live"

    op.execute(
        template_history_insert.format(
            template_id,
            template_name,
            "email",
            datetime.utcnow(),
            template_content,
            current_app.config["NOTIFY_SERVICE_ID"],
            template_subject,
            current_app.config["NOTIFY_USER_ID"],
            "normal",
        )
    )

    op.execute(
        template_insert.format(
            template_id,
            template_name,
            "email",
            datetime.utcnow(),
            template_content,
            current_app.config["NOTIFY_SERVICE_ID"],
            template_subject,
            current_app.config["NOTIFY_USER_ID"],
            "normal",
        )
    )


# If you are copying this migration, please remember about an insert to TemplateRedacted,
# which was not originally included here either by mistake or because it was before TemplateRedacted existed
# op.execute(
#     """
#         INSERT INTO template_redacted (template_id, redact_personalisation, updated_at, updated_by_id)
#         VALUES ('{}', '{}', '{}', '{}')
#         ;
#     """.format(template_id, False, datetime.utcnow(), current_app.config['NOTIFY_USER_ID'])
# )


def downgrade():
    op.execute("DELETE FROM notifications WHERE template_id = '{}'".format(template_id))
    op.execute("DELETE FROM notification_history WHERE template_id = '{}'".format(template_id))
    op.execute("DELETE FROM templates_history WHERE id = '{}'".format(template_id))
    op.execute("DELETE FROM templates WHERE id = '{}'".format(template_id))
