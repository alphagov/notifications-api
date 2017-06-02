from datetime import datetime

import pytest
from flask import json

from app.notifications.receive_notifications import (
    format_mmg_message,
    format_mmg_datetime,
    create_inbound_mmg_sms_object
)

from app.models import InboundSms
from tests.app.db import create_service


def test_receive_notification_returns_received_to_mmg(client, sample_service):
    data = {"ID": "1234",
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


def test_create_inbound_mmg_sms_object(sample_service):
    sample_service.sms_sender = 'foo'
    data = {
        'Message': 'hello+there+%F0%9F%93%A9',
        'Number': 'foo',
        'MSISDN': '07700 900 001',
        'DateRecieved': '2017-01-02+03%3A04%3A05',
        'ID': 'bar',
    }

    inbound_sms = create_inbound_mmg_sms_object(sample_service, data)

    assert inbound_sms.service_id == sample_service.id
    assert inbound_sms.notify_number == 'foo'
    assert inbound_sms.user_number == '447700900001'
    assert inbound_sms.provider_date == datetime(2017, 1, 2, 3, 4, 5)
    assert inbound_sms.provider_reference == 'bar'
    assert inbound_sms._content != 'hello there 📩'
    assert inbound_sms.content == 'hello there 📩'


@pytest.mark.parametrize('notify_number', ['foo', 'baz'], ids=['two_matching_services', 'no_matching_services'])
def test_receive_notification_error_if_not_single_matching_service(client, notify_db_session, notify_number):
    create_service(service_name='a', sms_sender='foo')
    create_service(service_name='b', sms_sender='foo')

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


def test_receive_notification_returns_received_to_firetext(client):
    data = "source=07999999999&destination=07111111111&message=this is a message&time=2017-01-01 12:00:00"

    response = client.post(
        path='/notifications/sms/receive/firetext',
        data=data,
        headers=[('Content-Type', 'application/x-www-form-urlencoded')])

    assert response.status_code == 200
    result = json.loads(response.get_data(as_text=True))

    assert result['status'] == 'ok'
