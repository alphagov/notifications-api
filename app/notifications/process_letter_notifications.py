from notifications_utils.postal_address import PostalAddress

from app import create_random_identifier
from app.models import LETTER_TYPE
from app.notifications.process_notifications import persist_notification


def create_letter_notification(
    letter_data,
    template,
    service,
    api_key,
    status,
    reply_to_text=None,
    billable_units=None,
    updated_at=None,
    postage=None
):
    notification = persist_notification(
        template_id=template.id,
        template_version=template.version,
        # we only accept addresses_with_underscores from the API (from CSV we also accept dashes, spaces etc)
        recipient=PostalAddress.from_personalisation(letter_data['personalisation']).normalised,
        service=service,
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
        # letter_data.get('postage') is only set for precompiled letters (if international it is set after sanitise)
        # letters from a template will pass in 'europe' or 'rest-of-world' if None then use postage from template
        postage=postage or letter_data.get('postage') or template.postage,
        updated_at=updated_at
    )
    return notification
