from datetime import datetime

import pytest

from app import DATETIME_FORMAT
from app.models import Notification, ServiceWhitelist


def test_should_build_notification_from_minimal_set_of_api_derived_params(notify_api):
    now = datetime.utcnow()

    notification = {
        'template': 'template',
        'template_version': '1',
        'to': 'someone',
        'personalisation': {}
    }
    notification = Notification.from_api_request(
        created_at=now.strftime(DATETIME_FORMAT),
        notification=notification,
        notification_id="notification_id",
        service_id="service_id",
        notification_type='SMS',
        api_key_id='api_key_id',
        key_type='key_type'
    )
    assert notification.created_at == now
    assert notification.id == "notification_id"
    assert notification.template_id == 'template'
    assert notification.template_version == '1'
    assert not notification.job_row_number
    assert not notification.job_id
    assert notification.to == 'someone'
    assert notification.service_id == 'service_id'
    assert notification.status == 'created'
    assert not notification.personalisation
    assert notification.notification_type == 'SMS'
    assert notification.api_key_id == 'api_key_id'
    assert notification.key_type == 'key_type'


def test_should_build_notification_from_full_set_of_api_derived_params(notify_api):
    now = datetime.utcnow()

    notification = {
        'template': 'template',
        'template_version': '1',
        'to': 'someone',
        'personalisation': {'key': 'value'},
        'job': 'job_id',
        'row_number': 100
    }
    notification = Notification.from_api_request(
        created_at=now.strftime(DATETIME_FORMAT),
        notification=notification,
        notification_id="notification_id",
        service_id="service_id",
        notification_type='SMS',
        api_key_id='api_key_id',
        key_type='key_type'
    )
    assert notification.created_at == now
    assert notification.id == "notification_id"
    assert notification.template_id == 'template'
    assert notification.template_version == '1'
    assert notification.job_row_number == 100
    assert notification.job_id == 'job_id'
    assert notification.to == 'someone'
    assert notification.service_id == 'service_id'
    assert notification.status == 'created'
    assert notification.personalisation == {'key': 'value'}
    assert notification.notification_type == 'SMS'
    assert notification.api_key_id == 'api_key_id'
    assert notification.key_type == 'key_type'


@pytest.mark.parametrize('mobile_number', [
    '07700 900678',
    '+44 7700 900678'
])
def test_should_build_service_whitelist_from_mobile_number(mobile_number):
    service_whitelist = ServiceWhitelist.from_string('service_id', mobile_number)

    assert service_whitelist.mobile_number == mobile_number
    assert service_whitelist.email_address is None

@pytest.mark.parametrize('email_address', [
    'test@example.com'
])
def test_should_build_service_whitelist_from_email_address(email_address):
    service_whitelist = ServiceWhitelist.from_string('service_id', email_address)

    assert service_whitelist.email_address == email_address
    assert service_whitelist.mobile_number is None


@pytest.mark.parametrize('contact', [
    '',
    '07700dsadsad',
    'gmail.com'
])
def test_should_not_build_service_whitelist_from_invalid_contact(contact):
    with pytest.raises(ValueError):
        ServiceWhitelist.from_string('service_id', contact)
