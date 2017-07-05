import uuid
from datetime import datetime
from unittest.mock import call

import pytest
from flask import json

from app.dao.services_dao import dao_fetch_services_by_sms_sender
from app.notifications.receive_notifications import (
    format_mmg_message,
    format_mmg_datetime,
    create_inbound_sms_object,
    strip_leading_forty_four
)

from app.models import InboundSms, EMAIL_TYPE, SMS_TYPE, INBOUND_SMS_TYPE
from tests.app.db import create_service
from tests.app.conftest import sample_service


def test_receive_notification_returns_received_to_mmg(client, mocker, sample_service_full_permissions):
    mocked = mocker.patch("app.notifications.receive_notifications.tasks.send_inbound_sms_to_service.apply_async")
    data = {
        "ID": "1234",
        "MSISDN": "447700900855",
        "Message": "Some message to notify",
        "Trigger": "Trigger?",
        "Number": "testing",
        "Channel": "SMS",
        "DateRecieved": "2012-06-27 12:33:00"
    }
    response = client.post(path='/notifications/sms/receive/mmg',
                           data=json.dumps(data),
                           headers=[('Content-Type', 'application/json')])

    assert response.status_code == 200
    assert response.get_data(as_text=True) == 'RECEIVED'
    inbound_sms_id = InboundSms.query.all()[0].id
    mocked.assert_called_once_with(
        [str(inbound_sms_id), str(sample_service_full_permissions.id)], queue="notify-internal-tasks")


@pytest.mark.parametrize('provider,headers,data,expected_response', [
    (
        'mmg',
        [('Content-Type', 'application/json')],
        json.dumps({
            "ID": "1234",
            "MSISDN": "447700900855",
            "Message": "Some message to notify",
            "Trigger": "Trigger?",
            "Number": "testing",
            "Channel": "SMS",
            "DateRecieved": "2012-06-27 12:33:00"
        }),
        'RECEIVED'
    ),
    (
        'firetext',
        None,
        {
            "Message": "Some message to notify",
            "source": "Source",
            "time": "2012-06-27 12:33:00",
            "destination": "447700900855"
        },
        '{\n  "status": "ok"\n}'
    ),
])
@pytest.mark.parametrize('permissions', [
    ([SMS_TYPE]),
    ([INBOUND_SMS_TYPE]),
])
def test_receive_notification_without_permissions_does_not_create_inbound(
        client, mocker, notify_db, notify_db_session, permissions, provider, headers, data, expected_response):
    service = sample_service(notify_db, notify_db_session, permissions=permissions)
    mocker.patch("app.notifications.receive_notifications.dao_fetch_services_by_sms_sender",
                 return_value=[service])
    mocked_send_inbound_sms = mocker.patch(
        "app.notifications.receive_notifications.tasks.send_inbound_sms_to_service.apply_async")
    mocked_logger = mocker.patch("flask.current_app.logger.error")

    response = client.post(path='/notifications/sms/receive/{}'.format(provider),
                           data=data,
                           headers=headers)

    assert response.status_code == 200
    assert response.get_data(as_text=True) == expected_response
    assert len(InboundSms.query.all()) == 0
    mocked_send_inbound_sms.assert_not_called()
    mocked_logger.assert_called_once_with('Service "{}" does not allow inbound SMS'.format(service.id))


@pytest.mark.parametrize('message, expected_output', [
    ('abc', 'abc'),
    ('', ''),
    ('lots+of+words', 'lots of words'),
    ('%F0%9F%93%A9+%F0%9F%93%A9+%F0%9F%93%A9', '📩 📩 📩'),
    ('x+%2B+y', 'x + y')
])
def test_format_mmg_message(message, expected_output):
    assert format_mmg_message(message) == expected_output


@pytest.mark.parametrize('provider_date, expected_output', [
    ('2017-01-21+11%3A56%3A11', datetime(2017, 1, 21, 11, 56, 11)),
    ('2017-05-21+11%3A56%3A11', datetime(2017, 5, 21, 10, 56, 11))
])
def test_format_mmg_datetime(provider_date, expected_output):
    assert format_mmg_datetime(provider_date) == expected_output


def test_create_inbound_mmg_sms_object(sample_service_full_permissions):
    sample_service_full_permissions.sms_sender = 'foo'
    data = {
        'Message': 'hello+there+%F0%9F%93%A9',
        'Number': 'foo',
        'MSISDN': '07700 900 001',
        'DateRecieved': '2017-01-02+03%3A04%3A05',
        'ID': 'bar',
    }

    inbound_sms = create_inbound_sms_object(sample_service_full_permissions, format_mmg_message(data["Message"]),
                                            data["MSISDN"], data["ID"], data["DateRecieved"], "mmg")

    assert inbound_sms.service_id == sample_service_full_permissions.id
    assert inbound_sms.notify_number == 'foo'
    assert inbound_sms.user_number == '447700900001'
    assert inbound_sms.provider_date == datetime(2017, 1, 2, 3, 4, 5)
    assert inbound_sms.provider_reference == 'bar'
    assert inbound_sms._content != 'hello there 📩'
    assert inbound_sms.content == 'hello there 📩'
    assert inbound_sms.provider == 'mmg'


@pytest.mark.parametrize('notify_number', ['foo', 'baz'], ids=['two_matching_services', 'no_matching_services'])
def test_receive_notification_error_if_not_single_matching_service(client, notify_db_session, notify_number):
    create_service(service_name='a', sms_sender='foo', service_permissions=[EMAIL_TYPE, SMS_TYPE, INBOUND_SMS_TYPE])
    create_service(service_name='b', sms_sender='foo', service_permissions=[EMAIL_TYPE, SMS_TYPE, INBOUND_SMS_TYPE])

    data = {
        'Message': 'hello',
        'Number': notify_number,
        'MSISDN': '7700900001',
        'DateRecieved': '2017-01-02 03:04:05',
        'ID': 'bar',
    }
    response = client.post(path='/notifications/sms/receive/mmg',
                           data=json.dumps(data),
                           headers=[('Content-Type', 'application/json')])

    # we still return 'RECEIVED' to MMG
    assert response.status_code == 200
    assert response.get_data(as_text=True) == 'RECEIVED'
    assert InboundSms.query.count() == 0


def test_receive_notification_returns_received_to_firetext(notify_db_session, client, mocker):
    mocked = mocker.patch("app.notifications.receive_notifications.tasks.send_inbound_sms_to_service.apply_async")
    mock = mocker.patch('app.notifications.receive_notifications.statsd_client.incr')

    service = create_service(
        service_name='b', sms_sender='07111111111', service_permissions=[EMAIL_TYPE, SMS_TYPE, INBOUND_SMS_TYPE])

    data = "source=07999999999&destination=07111111111&message=this is a message&time=2017-01-01 12:00:00"

    response = client.post(
        path='/notifications/sms/receive/firetext',
        data=data,
        headers=[('Content-Type', 'application/x-www-form-urlencoded')])

    assert response.status_code == 200
    result = json.loads(response.get_data(as_text=True))

    mock.assert_has_calls([call('inbound.firetext.successful')])

    assert result['status'] == 'ok'
    inbound_sms_id = InboundSms.query.all()[0].id
    mocked.assert_called_once_with([str(inbound_sms_id), str(service.id)], queue="notify-internal-tasks")


def test_receive_notification_from_firetext_persists_message(notify_db_session, client, mocker):
    mocked = mocker.patch("app.notifications.receive_notifications.tasks.send_inbound_sms_to_service.apply_async")
    mocker.patch('app.notifications.receive_notifications.statsd_client.incr')

    service = create_service(
        service_name='b', sms_sender='07111111111', service_permissions=[EMAIL_TYPE, SMS_TYPE, INBOUND_SMS_TYPE])

    data = "source=07999999999&destination=07111111111&message=this is a message&time=2017-01-01 12:00:00"

    response = client.post(
        path='/notifications/sms/receive/firetext',
        data=data,
        headers=[('Content-Type', 'application/x-www-form-urlencoded')])

    assert response.status_code == 200
    result = json.loads(response.get_data(as_text=True))

    persisted = InboundSms.query.first()

    assert result['status'] == 'ok'
    assert persisted.notify_number == '07111111111'
    assert persisted.user_number == '447999999999'
    assert persisted.service == service
    assert persisted.content == 'this is a message'
    assert persisted.provider == 'firetext'
    assert persisted.provider_date == datetime(2017, 1, 1, 12, 0, 0, 0)
    mocked.assert_called_once_with([str(persisted.id), str(service.id)], queue="notify-internal-tasks")


def test_receive_notification_from_firetext_persists_message_with_normalized_phone(notify_db_session, client, mocker):
    mocker.patch("app.notifications.receive_notifications.tasks.send_inbound_sms_to_service.apply_async")
    mock = mocker.patch('app.notifications.receive_notifications.statsd_client.incr')

    create_service(
        service_name='b', sms_sender='07111111111', service_permissions=[EMAIL_TYPE, SMS_TYPE, INBOUND_SMS_TYPE])

    data = "source=(+44)7999999999&destination=07111111111&message=this is a message&time=2017-01-01 12:00:00"

    response = client.post(
        path='/notifications/sms/receive/firetext',
        data=data,
        headers=[('Content-Type', 'application/x-www-form-urlencoded')])

    assert response.status_code == 200
    result = json.loads(response.get_data(as_text=True))

    persisted = InboundSms.query.first()

    assert result['status'] == 'ok'
    assert persisted.user_number == '447999999999'


def test_returns_ok_to_firetext_if_mismatched_sms_sender(notify_db_session, client, mocker):
    mocked = mocker.patch("app.notifications.receive_notifications.tasks.send_inbound_sms_to_service.apply_async")
    mock = mocker.patch('app.notifications.receive_notifications.statsd_client.incr')

    create_service(
        service_name='b', sms_sender='07111111199', service_permissions=[EMAIL_TYPE, SMS_TYPE, INBOUND_SMS_TYPE])

    data = "source=(+44)7999999999&destination=07111111111&message=this is a message&time=2017-01-01 12:00:00"

    response = client.post(
        path='/notifications/sms/receive/firetext',
        data=data,
        headers=[('Content-Type', 'application/x-www-form-urlencoded')])

    assert response.status_code == 200
    result = json.loads(response.get_data(as_text=True))

    assert not InboundSms.query.all()
    assert result['status'] == 'ok'
    mock.assert_has_calls([call('inbound.firetext.failed')])
    mocked.call_count == 0


@pytest.mark.parametrize(
    'number, expected',
    [
        ('447123123123', '07123123123'),
        ('447123123144', '07123123144'),
        ('07123123123', '07123123123'),
        ('447444444444', '07444444444')
    ]
)
def test_strip_leading_country_code(number, expected):
    assert strip_leading_forty_four(number) == expected
