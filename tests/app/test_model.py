import uuid
from datetime import datetime

import pytest

from app import DATETIME_FORMAT
from app.models import (
    Notification,
    ServiceWhitelist,
    MOBILE_TYPE, EMAIL_TYPE)


def test_should_build_notification_from_minimal_set_of_api_derived_params(notify_api):
    now = datetime.utcnow()

    notification = Notification.from_request(
        template_id='template',
        template_version='1',
        recipient='someone',
        service_id='service_id',
        notification_type='SMS',
        created_at=now,
        api_key_id='api_key_id',
        key_type='key_type',
        personalisation={},
        job_id=None,
        job_row_number=None
    )
    assert notification.created_at == now
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
    notification = Notification.from_request(template_id='template',
                                             template_version=1,
                                             recipient='someone',
                                             service_id='service_id',
                                             personalisation={'key': 'value'},
                                             notification_type='SMS',
                                             api_key_id='api_key_id',
                                             key_type='key_type',
                                             job_id='job_id',
                                             job_row_number=100,
                                             created_at=now
                                             )
    assert notification.created_at == now
    assert notification.id is None
    assert notification.template_id == 'template'
    assert notification.template_version == 1
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
