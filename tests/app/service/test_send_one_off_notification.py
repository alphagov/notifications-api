import uuid
from unittest.mock import Mock

import pytest
from notifications_utils.recipients import InvalidPhoneError

from app.v2.errors import BadRequestError, TooManyRequestsError
from app.celery import QueueNames
from app.service.send_notification import send_one_off_notification
from app.models import KEY_TYPE_NORMAL, PRIORITY, SMS_TYPE

from tests.app.db import create_user


@pytest.fixture
def persist_mock(mocker):
    noti = Mock(id=uuid.uuid4())
    return mocker.patch('app.service.send_notification.persist_notification', return_value=noti)


@pytest.fixture
def celery_mock(mocker):
    return mocker.patch('app.service.send_notification.send_notification_to_queue')


def test_send_one_off_notification_calls_celery_correctly(persist_mock, celery_mock, sample_template):
    service = sample_template.service

    post_data = {
        'template_id': str(sample_template.id),
        'to': '07700 900 001',
        'created_by': str(service.created_by_id)
    }

    resp = send_one_off_notification(service.id, post_data)

    assert resp == {
        'id': str(persist_mock.return_value.id)
    }

    celery_mock.assert_called_once_with(
        notification=persist_mock.return_value,
        research_mode=False,
        queue=None
    )


def test_send_one_off_notification_calls_persist_correctly(
    persist_mock,
    celery_mock,
    sample_template_with_placeholders
):
    template = sample_template_with_placeholders
    service = template.service

    post_data = {
        'template_id': str(template.id),
        'to': '07700 900 001',
        'personalisation': {'name': 'foo'},
        'created_by': str(service.created_by_id)
    }

    send_one_off_notification(service.id, post_data)

    persist_mock.assert_called_once_with(
        template_id=template.id,
        template_version=template.version,
        recipient=post_data['to'],
        service=template.service,
        personalisation={'name': 'foo'},
        notification_type=SMS_TYPE,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
        created_by_id=str(service.created_by_id)
    )


def test_send_one_off_notification_honors_research_mode(persist_mock, celery_mock, sample_template):
    service = sample_template.service
    service.research_mode = True

    post_data = {
        'template_id': str(sample_template.id),
        'to': '07700 900 001',
        'created_by': str(service.created_by_id)
    }

    send_one_off_notification(service.id, post_data)

    assert celery_mock.call_args[1]['research_mode'] is True


def test_send_one_off_notification_honors_priority(persist_mock, celery_mock, sample_template):
    service = sample_template.service
    sample_template.process_type = PRIORITY

    post_data = {
        'template_id': str(sample_template.id),
        'to': '07700 900 001',
        'created_by': str(service.created_by_id)
    }

    send_one_off_notification(service.id, post_data)

    assert celery_mock.call_args[1]['queue'] == QueueNames.PRIORITY


def test_send_one_off_notification_raises_if_invalid_recipient(sample_template):
    service = sample_template.service

    post_data = {
        'template_id': str(sample_template.id),
        'to': 'not a phone number',
        'created_by': str(service.created_by_id)
    }

    with pytest.raises(InvalidPhoneError):
        send_one_off_notification(service.id, post_data)


def test_send_one_off_notification_raises_if_cant_send_to_recipient(sample_template):
    service = sample_template.service
    service.restricted = True

    post_data = {
        'template_id': str(sample_template.id),
        'to': '07700 900 001',
        'created_by': str(service.created_by_id)
    }

    with pytest.raises(BadRequestError) as e:
        send_one_off_notification(service.id, post_data)

    assert 'service is in trial mode' in e.value.message


def test_send_one_off_notification_raises_if_over_limit(sample_template):
    service = sample_template.service
    service.message_limit = 0

    post_data = {
        'template_id': str(sample_template.id),
        'to': '07700 900 001',
        'created_by': str(service.created_by_id)
    }

    with pytest.raises(TooManyRequestsError):
        send_one_off_notification(service.id, post_data)


def test_send_one_off_notification_raises_if_message_too_long(persist_mock, sample_template_with_placeholders):
    template = sample_template_with_placeholders
    service = template.service

    post_data = {
        'template_id': str(template.id),
        'to': '07700 900 001',
        'personalisation': {'name': '🚫' * 500},
        'created_by': str(service.created_by_id)
    }

    with pytest.raises(BadRequestError) as e:
        send_one_off_notification(service.id, post_data)

    assert e.value.message == 'Content for template has a character count greater than the limit of 495'


def test_send_one_off_notification_fails_if_created_by_other_service(sample_template):
    user_not_in_service = create_user(email='some-other-user@gov.uk')

    post_data = {
        'template_id': str(sample_template.id),
        'to': '07700 900 001',
        'created_by': str(user_not_in_service.id)
    }

    with pytest.raises(BadRequestError) as e:
        send_one_off_notification(sample_template.service_id, post_data)

    assert e.value.message == 'Can’t create notification - Test User is not part of the "Sample service" service'
