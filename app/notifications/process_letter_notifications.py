from app import create_random_identifier
from app.models import LETTER_TYPE
from app.notifications.process_notifications import persist_notification


def create_letter_notification(letter_data, template, api_key, status, reply_to_text=None, billable_units=None):
    notification = persist_notification(
        template_id=template.id,
        template_version=template.version,
        # we only accept addresses_with_underscores from the API (from CSV we also accept dashes, spaces etc)
        recipient=letter_data['personalisation']['address_line_1'],
        service=template.service,
        personalisation=letter_data['personalisation'],
        notification_type=LETTER_TYPE,
        api_key_id=api_key.id,
        key_type=api_key.key_type,
        job_id=None,
        job_row_number=None,
        reference=create_random_identifier(),
        client_reference=letter_data.get('reference'),
        status=status,
        reply_to_text=reply_to_text,
        billable_units=billable_units,
        postage=letter_data.get('postage')
    )
    return notification
