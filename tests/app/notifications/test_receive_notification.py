import base64
from datetime import datetime
from unittest.mock import call

import pytest
from flask import json

from app.notifications.receive_notifications import (
    format_mmg_message,
    format_mmg_datetime,
    create_inbound_sms_object,
    strip_leading_forty_four,
    has_inbound_sms_permissions,
    unescape_string,
)

from app.models import InboundSms, EMAIL_TYPE, SMS_TYPE, INBOUND_SMS_TYPE
from tests.conftest import set_config
from tests.app.db import create_inbound_number, create_service, create_service_with_inbound_number
from tests.app.conftest import sample_service


def firetext_post(client, data, auth=True, password='testkey'):
    headers = [
        ('Content-Type', 'application/x-www-form-urlencoded'),
        ('X-Forwarded-For', '203.0.113.195, 70.41.3.18, 150.172.238.178')
    ]

    if auth:
        auth_value = base64.b64encode("notify:{}".format(password).encode('utf-8')).decode('utf-8')
        headers.append(('Authorization', 'Basic ' + auth_value))

    return client.post(
        path='/notifications/sms/receive/firetext',
        data=data,
        headers=headers
    )


def mmg_post(client, data, auth=True, password='testkey'):
    headers = [
        ('Content-Type', 'application/json'),
        ('X-Forwarded-For', '203.0.113.195, 70.41.3.18, 150.172.238.178')
    ]

    if auth:
        auth_value = base64.b64encode("notify:{}".format(password).encode('utf-8')).decode('utf-8')
        headers.append(('Authorization', 'Basic ' + auth_value))

    return client.post(
        path='/notifications/sms/receive/mmg',
        data=json.dumps(data),
        headers=headers
    )


def test_receive_notification_returns_received_to_mmg(client, mocker, sample_service_full_permissions):
    mocked = mocker.patch("app.notifications.receive_notifications.tasks.send_inbound_sms_to_service.apply_async")
    data = {
        "ID": "1234",
        "MSISDN": "447700900855",
        "Message": "Some message to notify",
        "Trigger": "Trigger?",
        "Number": sample_service_full_permissions.get_inbound_number(),
        "Channel": "SMS",
        "DateRecieved": "2012-06-27 12:33:00"
    }
    response = mmg_post(client, data)

    assert response.status_code == 200
    result = json.loads(response.get_data(as_text=True))
    assert result['status'] == 'ok'

    inbound_sms_id = InboundSms.query.all()[0].id
    mocked.assert_called_once_with(
        [str(inbound_sms_id), str(sample_service_full_permissions.id)], queue="notify-internal-tasks")


@pytest.mark.parametrize('permissions', [
    [SMS_TYPE],
    [INBOUND_SMS_TYPE],
])
def test_receive_notification_from_mmg_without_permissions_does_not_persist(
    client,
    mocker,
    notify_db_session,
    permissions
):
    mocked = mocker.patch("app.notifications.receive_notifications.tasks.send_inbound_sms_to_service.apply_async")
    create_service_with_inbound_number(inbound_number='07111111111', service_permissions=permissions)
    data = {
        "ID": "1234",
        "MSISDN": "07111111111",
        "Message": "Some message to notify",
        "Trigger": "Trigger?",
        "Number": "testing",
        "Channel": "SMS",
        "DateRecieved": "2012-06-27 12:33:00"
    }
    response = mmg_post(client, data)

    assert response.status_code == 200
    assert response.get_data(as_text=True) == 'RECEIVED'
    assert InboundSms.query.count() == 0
    assert mocked.called is False


@pytest.mark.parametrize('permissions', [
    [SMS_TYPE],
    [INBOUND_SMS_TYPE],
])
def test_receive_notification_from_firetext_without_permissions_does_not_persist(
    client,
    mocker,
    notify_db_session,
    permissions
):
    service = create_service_with_inbound_number(inbound_number='07111111111', service_permissions=permissions)
    mocker.patch("app.notifications.receive_notifications.dao_fetch_service_by_inbound_number",
                 return_value=service)
    mocked_send_inbound_sms = mocker.patch(
        "app.notifications.receive_notifications.tasks.send_inbound_sms_to_service.apply_async")
    mocker.patch("app.notifications.receive_notifications.has_inbound_sms_permissions", return_value=False)

    data = "source=07999999999&destination=07111111111&message=this is a message&time=2017-01-01 12:00:00"
    response = firetext_post(client, data)

    assert response.status_code == 200
    result = json.loads(response.get_data(as_text=True))

    assert result['status'] == 'ok'
    assert InboundSms.query.count() == 0
    assert not mocked_send_inbound_sms.called


def test_receive_notification_without_permissions_does_not_create_inbound_even_with_inbound_number_set(
        client, mocker, notify_db, notify_db_session):
    service = sample_service(notify_db, notify_db_session, permissions=[SMS_TYPE])
    inbound_number = create_inbound_number('1', service_id=service.id, active=True)

    mocked_send_inbound_sms = mocker.patch(
        "app.notifications.receive_notifications.tasks.send_inbound_sms_to_service.apply_async")
    mocked_has_permissions = mocker.patch(
        "app.notifications.receive_notifications.has_inbound_sms_permissions", return_value=False)

    data = {
        "ID": "1234",
        "MSISDN": "447700900855",
        "Message": "Some message to notify",
        "Trigger": "Trigger?",
        "Number": inbound_number.number,
        "Channel": "SMS",
        "DateRecieved": "2012-06-27 12:33:00"
    }

    response = mmg_post(client, data)

    assert response.status_code == 200
    assert len(InboundSms.query.all()) == 0
    assert mocked_has_permissions.called
    mocked_send_inbound_sms.assert_not_called()


@pytest.mark.parametrize('permissions,expected_response', [
    ([SMS_TYPE, INBOUND_SMS_TYPE], True),
    ([INBOUND_SMS_TYPE], False),
    ([SMS_TYPE], False),
])
def test_check_permissions_for_inbound_sms(notify_db, notify_db_session, permissions, expected_response):
    service = create_service(service_permissions=permissions)
    assert has_inbound_sms_permissions(service.permissions) is expected_response


@pytest.mark.parametrize('message, expected_output', [
    ('abc', 'abc'),
    ('', ''),
    ('lots+of+words', 'lots of words'),
    ('%F0%9F%93%A9+%F0%9F%93%A9+%F0%9F%93%A9', '📩 📩 📩'),
    ('x+%2B+y', 'x + y')
])
def test_format_mmg_message(message, expected_output):
    assert format_mmg_message(message) == expected_output


@pytest.mark.parametrize('raw, expected', [
    (
        '😬',
        '😬',
    ),
    (
        '1\\n2',
        '1\n2',
    ),
    (
        '\\\'"\\\'',
        '\'"\'',
    ),
    (
        """

        """,
        """

        """,
    ),
    (
        '\x79 \\x79 \\\\x79',  # we should never see the middle one
        'y y \\x79',
    ),
])
def test_unescape_string(raw, expected):
    assert unescape_string(raw) == expected


@pytest.mark.parametrize('provider_date, expected_output', [
    ('2017-01-21+11%3A56%3A11', datetime(2017, 1, 21, 11, 56, 11)),
    ('2017-05-21+11%3A56%3A11', datetime(2017, 5, 21, 10, 56, 11))
])
def test_format_mmg_datetime(provider_date, expected_output):
    assert format_mmg_datetime(provider_date) == expected_output


def test_create_inbound_mmg_sms_object(sample_service_full_permissions):
    data = {
        'Message': 'hello+there+%F0%9F%93%A9',
        'Number': sample_service_full_permissions.get_inbound_number(),
        'MSISDN': '07700 900 001',
        'DateRecieved': '2017-01-02+03%3A04%3A05',
        'ID': 'bar',
    }

    inbound_sms = create_inbound_sms_object(sample_service_full_permissions, format_mmg_message(data["Message"]),
                                            data["MSISDN"], data["ID"], data["DateRecieved"], "mmg")

    assert inbound_sms.service_id == sample_service_full_permissions.id
    assert inbound_sms.notify_number == sample_service_full_permissions.get_inbound_number()
    assert inbound_sms.user_number == '447700900001'
    assert inbound_sms.provider_date == datetime(2017, 1, 2, 3, 4, 5)
    assert inbound_sms.provider_reference == 'bar'
    assert inbound_sms._content != 'hello there 📩'
    assert inbound_sms.content == 'hello there 📩'
    assert inbound_sms.provider == 'mmg'


def test_create_inbound_mmg_sms_object_uses_inbound_number_if_set(sample_service_full_permissions):
    sample_service_full_permissions.sms_sender = 'foo'
    inbound_number = sample_service_full_permissions.get_inbound_number()

    data = {
        'Message': 'hello+there+%F0%9F%93%A9',
        'Number': sample_service_full_permissions.get_inbound_number(),
        'MSISDN': '07700 900 001',
        'DateRecieved': '2017-01-02+03%3A04%3A05',
        'ID': 'bar',
    }

    inbound_sms = create_inbound_sms_object(
        sample_service_full_permissions,
        format_mmg_message(data["Message"]),
        data["MSISDN"],
        data["ID"],
        data["DateRecieved"],
        "mmg"
    )

    assert inbound_sms.service_id == sample_service_full_permissions.id
    assert inbound_sms.notify_number == inbound_number


@pytest.mark.parametrize('notify_number', ['foo', 'baz'], ids=['two_matching_services', 'no_matching_services'])
def test_receive_notification_error_if_not_single_matching_service(client, notify_db_session, notify_number):
    create_service_with_inbound_number(
        inbound_number='dog',
        service_name='a',
        service_permissions=[EMAIL_TYPE, SMS_TYPE, INBOUND_SMS_TYPE]
    )
    create_service_with_inbound_number(
        inbound_number='bar',
        service_name='b',
        service_permissions=[EMAIL_TYPE, SMS_TYPE, INBOUND_SMS_TYPE]
    )

    data = {
        'Message': 'hello',
        'Number': notify_number,
        'MSISDN': '7700900001',
        'DateRecieved': '2017-01-02 03:04:05',
        'ID': 'bar',
    }
    response = mmg_post(client, data)

    # we still return 'RECEIVED' to MMG
    assert response.status_code == 200
    assert response.get_data(as_text=True) == 'RECEIVED'
    assert InboundSms.query.count() == 0


def test_receive_notification_returns_received_to_firetext(notify_db_session, client, mocker):
    mocked = mocker.patch("app.notifications.receive_notifications.tasks.send_inbound_sms_to_service.apply_async")
    mock = mocker.patch('app.notifications.receive_notifications.statsd_client.incr')

    service = create_service_with_inbound_number(
        service_name='b', inbound_number='07111111111', service_permissions=[EMAIL_TYPE, SMS_TYPE, INBOUND_SMS_TYPE])

    data = "source=07999999999&destination=07111111111&message=this is a message&time=2017-01-01 12:00:00"

    response = firetext_post(client, data)

    assert response.status_code == 200
    result = json.loads(response.get_data(as_text=True))

    mock.assert_has_calls([call('inbound.firetext.successful')])

    assert result['status'] == 'ok'
    inbound_sms_id = InboundSms.query.all()[0].id
    mocked.assert_called_once_with([str(inbound_sms_id), str(service.id)], queue="notify-internal-tasks")


def test_receive_notification_from_firetext_persists_message(notify_db_session, client, mocker):
    mocked = mocker.patch("app.notifications.receive_notifications.tasks.send_inbound_sms_to_service.apply_async")
    mocker.patch('app.notifications.receive_notifications.statsd_client.incr')

    service = create_service_with_inbound_number(
        inbound_number='07111111111',
        service_name='b',
        service_permissions=[EMAIL_TYPE, SMS_TYPE, INBOUND_SMS_TYPE])

    data = "source=07999999999&destination=07111111111&message=this is a message&time=2017-01-01 12:00:00"

    response = firetext_post(client, data)

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
    mocker.patch('app.notifications.receive_notifications.statsd_client.incr')

    create_service_with_inbound_number(
        inbound_number='07111111111', service_name='b', service_permissions=[EMAIL_TYPE, SMS_TYPE, INBOUND_SMS_TYPE])

    data = "source=(+44)7999999999&destination=07111111111&message=this is a message&time=2017-01-01 12:00:00"

    response = firetext_post(client, data)

    assert response.status_code == 200
    result = json.loads(response.get_data(as_text=True))

    persisted = InboundSms.query.first()

    assert result['status'] == 'ok'
    assert persisted.user_number == '447999999999'


def test_returns_ok_to_firetext_if_mismatched_sms_sender(notify_db_session, client, mocker):
    mocked = mocker.patch("app.notifications.receive_notifications.tasks.send_inbound_sms_to_service.apply_async")
    mock = mocker.patch('app.notifications.receive_notifications.statsd_client.incr')

    create_service_with_inbound_number(
        inbound_number='07111111199', service_name='b', service_permissions=[EMAIL_TYPE, SMS_TYPE, INBOUND_SMS_TYPE])

    data = "source=(+44)7999999999&destination=07111111111&message=this is a message&time=2017-01-01 12:00:00"

    response = firetext_post(client, data)

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


@pytest.mark.parametrize("auth, keys, status_code", [
    ["testkey", ["testkey"], 200],
    ["", ["testkey"], 401],
    ["wrong", ["testkey"], 403],
    ["testkey1", ["testkey1", "testkey2"], 200],
    ["testkey2", ["testkey1", "testkey2"], 200],
    ["wrong", ["testkey1", "testkey2"], 403],
    ["", [], 401],
    ["testkey", [], 403],
])
def test_firetext_inbound_sms_auth(notify_db_session, notify_api, client, mocker, auth, keys, status_code):
    mocker.patch("app.notifications.receive_notifications.tasks.send_inbound_sms_to_service.apply_async")

    create_service_with_inbound_number(
        service_name='b', inbound_number='07111111111', service_permissions=[EMAIL_TYPE, SMS_TYPE, INBOUND_SMS_TYPE]
    )

    data = "source=07999999999&destination=07111111111&message=this is a message&time=2017-01-01 12:00:00"

    with set_config(notify_api, 'FIRETEXT_INBOUND_SMS_AUTH', keys):
        response = firetext_post(client, data, auth=bool(auth), password=auth)
        assert response.status_code == status_code


@pytest.mark.parametrize("auth, keys, status_code", [
    ["testkey", ["testkey"], 200],
    ["", ["testkey"], 401],
    ["wrong", ["testkey"], 403],
    ["testkey1", ["testkey1", "testkey2"], 200],
    ["testkey2", ["testkey1", "testkey2"], 200],
    ["wrong", ["testkey1", "testkey2"], 403],
    ["", [], 401],
    ["testkey", [], 403],
])
@pytest.mark.skip(reason="aborts are disabled at the moment")
def test_mmg_inbound_sms_auth(notify_db_session, notify_api, client, mocker, auth, keys, status_code):
    mocker.patch("app.notifications.receive_notifications.tasks.send_inbound_sms_to_service.apply_async")

    create_service_with_inbound_number(
        service_name='b', inbound_number='07111111111', service_permissions=[EMAIL_TYPE, SMS_TYPE, INBOUND_SMS_TYPE]
    )

    data = "source=07999999999&destination=07111111111&message=this is a message&time=2017-01-01 12:00:00"

    with set_config(notify_api, 'MMG_INBOUND_SMS_AUTH', keys):
        response = mmg_post(client, data, auth=bool(auth), password=auth)
        assert response.status_code == status_code


def test_create_inbound_sms_object_works_with_alphanumeric_sender(sample_service_full_permissions):
    data = {
        'Message': 'hello',
        'Number': sample_service_full_permissions.get_inbound_number(),
        'MSISDN': 'ALPHANUM3R1C',
        'DateRecieved': '2017-01-02+03%3A04%3A05',
        'ID': 'bar',
    }

    inbound_sms = create_inbound_sms_object(
        service=sample_service_full_permissions,
        content=format_mmg_message(data["Message"]),
        from_number='ALPHANUM3R1C',
        provider_ref='foo',
        date_received=None,
        provider_name="mmg"
    )

    assert inbound_sms.user_number == 'ALPHANUM3R1C'
