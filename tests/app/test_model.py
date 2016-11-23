import pytest
from datetime import datetime

from tests.app.conftest import sample_notification, sample_provider_rate
from app.models import (
    Notification,
    ServiceWhitelist,
    MOBILE_TYPE, EMAIL_TYPE)


@pytest.mark.parametrize('mobile_number', [
    '07700 900678',
    '+44 7700 900678'
])
def test_should_build_service_whitelist_from_mobile_number(mobile_number):
    service_whitelist = ServiceWhitelist.from_string('service_id', MOBILE_TYPE, mobile_number)

    assert service_whitelist.recipient == mobile_number


@pytest.mark.parametrize('email_address', [
    'test@example.com'
])
def test_should_build_service_whitelist_from_email_address(email_address):
    service_whitelist = ServiceWhitelist.from_string('service_id', EMAIL_TYPE, email_address)

    assert service_whitelist.recipient == email_address


@pytest.mark.parametrize('contact, recipient_type', [
    ('', None),
    ('07700dsadsad', MOBILE_TYPE),
    ('gmail.com', EMAIL_TYPE)
])
def test_should_not_build_service_whitelist_from_invalid_contact(recipient_type, contact):
    with pytest.raises(ValueError):
        ServiceWhitelist.from_string('service_id', recipient_type, contact)


@pytest.mark.parametrize('provider, billable_units, expected_cost', [
    ('mmg', 1, 3.5),
    ('firetext', 2, 5),
    ('ses', 0, 0)
])
def test_calculate_cost_from_notification_billable_units(
        notify_db, notify_db_session, provider, billable_units, expected_cost
):
    provider_rates = [
        ('mmg', datetime(2016, 7, 1), 1.5),
        ('firetext', datetime(2016, 7, 1), 2.5),
        ('mmg', datetime.utcnow(), 3.5),
    ]
    for provider_identifier, valid_from, rate in provider_rates:
        sample_provider_rate(
            notify_db,
            notify_db_session,
            provider_identifier=provider_identifier,
            valid_from=valid_from,
            rate=rate
        )

    notification = sample_notification(notify_db, notify_db_session, billable_units=billable_units, sent_by=provider)
    assert notification.cost() == expected_cost
