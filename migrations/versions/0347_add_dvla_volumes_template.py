"""

Revision ID: 0347_add_dvla_volumes_template
Revises: 0346_notify_number_sms_sender
Create Date: 2021-02-15 15:36:34.654275

"""

import os
from datetime import UTC, datetime

from alembic import op
from flask import current_app

revision = "0347_add_dvla_volumes_template"
down_revision = "0346_notify_number_sms_sender"

email_template_id = "11fad854-fd38-4a7c-bd17-805fb13dfc12"
environment = os.environ["NOTIFY_ENVIRONMENT"]


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

    email_template_content = "\n".join(
        [
            "((total_volume)) letters (((total_sheets)) sheets) sent via Notify are coming in today''s batch. These include: ",
            "",
            "((first_class_volume)) first class letters (((first_class_sheets)) sheets).",
            "((second_class_volume)) second class letters (((second_class_sheets)) sheets).",
            "((international_volume)) international letters (((international_sheets)) sheets).",
            "",
            "Thanks",
            "",
            "GOV.​UK Notify team",
            "https://www.gov.uk/notify",
        ]
    )

    email_template_name = "Notify daily letter volumes"
    email_template_subject = "Notify letter volume for ((date)): ((total_volume)) letters, ((total_sheets)) sheets"

    op.execute(
        template_history_insert.format(
            email_template_id,
            email_template_name,
            "email",
            datetime.now(UTC).replace(tzinfo=None),
            email_template_content,
            current_app.config["NOTIFY_SERVICE_ID"],
            email_template_subject,
            current_app.config["NOTIFY_USER_ID"],
            "normal",
        )
    )

    op.execute(
        template_insert.format(
            email_template_id,
            email_template_name,
            "email",
            datetime.now(UTC).replace(tzinfo=None),
            email_template_content,
            current_app.config["NOTIFY_SERVICE_ID"],
            email_template_subject,
            current_app.config["NOTIFY_USER_ID"],
            "normal",
        )
    )


def downgrade():
    if environment not in ["live", "production"]:
        op.execute("DELETE FROM notifications WHERE template_id = '{}'".format(email_template_id))
        op.execute("DELETE FROM notification_history WHERE template_id = '{}'".format(email_template_id))
        op.execute("DELETE FROM template_redacted WHERE template_id = '{}'".format(email_template_id))
        op.execute("DELETE FROM templates_history WHERE id = '{}'".format(email_template_id))
        op.execute("DELETE FROM templates WHERE id = '{}'".format(email_template_id))
