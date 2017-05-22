from datetime import datetime

import pytest
from flask import json
import freezegun

from app.notifications.receive_notifications import (
    format_message,
    create_inbound_sms_object
)


def test_receive_notification_returns_received_to_mmg(client, sample_service):
    data = {"ID": "1234",
            "MSISDN": "447700900855",
            "Message": "Some message to notify",
            "Trigger": "Trigger?",
            "Number": "testing",
            "Channel": "SMS",
            "DateReceived": "2012-06-27 12:33:00"
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
def test_format_message(message, expected_output):
    assert format_message(message) == expected_output


def test_create_inbound_sms_object(sample_service):
    sample_service.sms_sender = 'foo'
    data = {
        'Message': 'hello+there+%F0%9F%93%A9',
        'Number': 'foo',
        'MSISDN': '07700 900 001',
        'DateReceived': '2017-01-02 03:04:05',
        'ID': 'bar',
    }

    inbound_sms = create_inbound_sms_object(sample_service, data)

    assert inbound_sms.service_id == sample_service.id
    assert inbound_sms.notify_number == 'foo'
    assert inbound_sms.user_number == '7700900001'
    assert inbound_sms.provider_date == datetime(2017, 1, 2, 3, 4, 5)
    assert inbound_sms.provider_reference == 'bar'
    assert inbound_sms._content != 'hello there 📩'
    assert inbound_sms.content == 'hello there 📩'
