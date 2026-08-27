"""
Create Date: 2026-08-27 13:08:56.078517
"""
import textwrap

from flask import current_app
from alembic import op

revision = '0561_add_go_live_admin_template'
down_revision = '0560_add_nhs_notify_org'

template_id = "999813a9-d7d2-4b61-bc68-73b59937ca4e"
template_content = textwrap.dedent(
    """\
    Hi ((name))

    This email contains important information about GOV.UK Notify:

    * keep it somewhere you can find it
    * do not share it outside your team

    # Managing your GOV.UK Notify service

    We sent you this email because you have the ‘manage settings, team and usage’ permission for the following service:

    ^((service name))

    For a full list of your responsibilities, see: [About the ‘manage settings’ permission](https://www.notifications.service.gov.uk/using-notify/team-members-and-permissions#manage-settings)

    ---

    # 1. Look after your team

    Make sure there are always at least 2 active team members with the ‘manage settings, team and usage’ permission.

    ## If a team member’s sign-in details have changed

    It’s your responsibility to update their email address or phone number.

    They do not need to contact support.

    ---

    # 2. If you send text messages or letters

    You are responsible for making sure your organisation sends us a purchase order.

    See: [How to pay](https://www.notifications.service.gov.uk/pricing/how-to-pay).

    ---

    # 3. How to use GOV.UK Notify support

    ## Subscribe to our status page

    You do not need to contact us if your problem is already listed on the [status page](https://status.notifications.service.gov.uk/).

    ## If you get stuck

    Read our [guidance pages](https://www.notifications.service.gov.uk/using-notify).

    ## Reporting a problem

    [Use the support page to report a problem](https://www.notifications.service.gov.uk/support)

    GOV.UK Notify provides 24/7 support for live services.

    We’ll triage your enquiry and respond:

    * within 30 minutes if it qualifies as an emergency
    * by the end of the next working day for everything else

    ## If the support page is not working

    Do not contact us unless you see one of the following errors:

    * a ‘technical difficulties’ error when you try to send a message
    * a 500 response code when you try to send messages using the API

    If you see one of these errors and you cannot use the support page, you can email: ooh-gov-uk-notify-support@digital.cabinet-office.gov.uk

    Do not use this email address for any other problems or questions.

    Never share this email address with people outside your team.

    ---

    Kind regards

    GOV.​UK Notify
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
                service_id,
                created_by_id,
                version,
                archived,
                hidden,
                has_unsubscribe_link
            )
            VALUES (
                '{template_id}',
                'Managing your GOV.UK Notify service',
                'email',
                current_timestamp,
                'Important: Managing your GOV.UK Notify service',
                '{template_content}',
                '{current_app.config["NOTIFY_SERVICE_ID"]}',
                '{current_app.config["NOTIFY_USER_ID"]}',
                1,
                false,
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
    for table, column_name in (
        ("notifications", "template_id"),
        ("notification_history", "template_id"),
        ("template_redacted", "template_id"),
        ("template_folder_map", "template_id"),
        ("templates", "id"),
        ("templates_history", "id"),
    ):
        op.execute(f"DELETE FROM {table} WHERE {column_name} = '{template_id}'")
