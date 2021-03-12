from app.models import LETTER_TYPE, NOTIFICATION_CREATED, Notification
from app.notifications.process_letter_notifications import (
    create_letter_notification,
)
from app.serialised_models import SerialisedTemplate


def test_create_letter_notification_creates_notification(sample_letter_template, sample_api_key):
    data = {
        'personalisation': {
            'address_line_1': 'The Queen',
            'address_line_2': 'Buckingham Palace',
            'postcode': 'SW1 1AA',
        }
    }

    template = SerialisedTemplate.from_id_and_service_id(
        sample_letter_template.id, sample_letter_template.service_id
    )

    notification = create_letter_notification(
        data,
        template,
        sample_letter_template.service,
        sample_api_key,
        NOTIFICATION_CREATED,
    )

    assert notification == Notification.query.one()
    assert notification.job is None
    assert notification.status == NOTIFICATION_CREATED
    assert notification.template_id == sample_letter_template.id
    assert notification.template_version == sample_letter_template.version
    assert notification.api_key == sample_api_key
    assert notification.notification_type == LETTER_TYPE
    assert notification.key_type == sample_api_key.key_type
    assert notification.reference is not None
    assert notification.client_reference is None
    assert notification.postage == 'second'


def test_create_letter_notification_sets_reference(sample_letter_template, sample_api_key):
    data = {
        'personalisation': {
            'address_line_1': 'The Queen',
            'address_line_2': 'Buckingham Palace',
            'postcode': 'SW1 1AA',
        },
        'reference': 'foo'
    }

    template = SerialisedTemplate.from_id_and_service_id(
        sample_letter_template.id, sample_letter_template.service_id
    )

    notification = create_letter_notification(
        data,
        template,
        sample_letter_template.service,
        sample_api_key,
        NOTIFICATION_CREATED,
    )

    assert notification.client_reference == 'foo'


def test_create_letter_notification_sets_billable_units(sample_letter_template, sample_api_key):
    data = {
        'personalisation': {
            'address_line_1': 'The Queen',
            'address_line_2': 'Buckingham Palace',
            'postcode': 'SW1 1AA',
        },
    }

    template = SerialisedTemplate.from_id_and_service_id(
        sample_letter_template.id, sample_letter_template.service_id
    )

    notification = create_letter_notification(
        data,
        template,
        sample_letter_template.service,
        sample_api_key,
        NOTIFICATION_CREATED,
        billable_units=3,
    )

    assert notification.billable_units == 3
