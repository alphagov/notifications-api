import uuid
from unittest.mock import ANY

import pytest
from flask import json

from app.config import QueueNames
from app.celery.research_mode_tasks import (
    send_sms_response,
    send_email_response,
    mmg_callback,
    firetext_callback,
    ses_notification_callback,
)


def test_make_mmg_callback(notify_api, rmock):
    endpoint = "http://localhost:6011/notifications/sms/mmg"
    rmock.request(
        "POST",
        endpoint,
        json={"status": "success"},
        status_code=200)
    send_sms_response("mmg", "1234", "07700900001")

    assert rmock.called
    assert rmock.request_history[0].url == endpoint
    assert json.loads(rmock.request_history[0].text)['MSISDN'] == '07700900001'


@pytest.mark.parametrize("phone_number",
                         ["07700900001", "07700900002", "07700900003",
                          "07700900236"])
def test_make_firetext_callback(notify_api, rmock, phone_number):
    endpoint = "http://localhost:6011/notifications/sms/firetext"
    rmock.request(
        "POST",
        endpoint,
        json="some data",
        status_code=200)
    send_sms_response("firetext", "1234", phone_number)

    assert rmock.called
    assert rmock.request_history[0].url == endpoint
    assert 'mobile={}'.format(phone_number) in rmock.request_history[0].text


def test_make_ses_callback(notify_api, mocker):
    mock_task = mocker.patch('app.celery.research_mode_tasks.process_ses_results')
    some_ref = str(uuid.uuid4())

    send_email_response(reference=some_ref, to="test@test.com")

    mock_task.apply_async.assert_called_once_with(ANY, queue=QueueNames.RESEARCH_MODE)
    assert mock_task.apply_async.call_args[0][0][0] == ses_notification_callback(some_ref)


@pytest.mark.parametrize("phone_number", ["07700900001", "+447700900001", "7700900001", "+44 7700900001",
                                          "+447700900236"])
def test_delivered_mmg_callback(phone_number):
    data = json.loads(mmg_callback("1234", phone_number))
    assert data['MSISDN'] == phone_number
    assert data['status'] == "3"
    assert data['reference'] == "mmg_reference"
    assert data['CID'] == "1234"


@pytest.mark.parametrize("phone_number", ["07700900002", "+447700900002", "7700900002", "+44 7700900002"])
def test_perm_failure_mmg_callback(phone_number):
    data = json.loads(mmg_callback("1234", phone_number))
    assert data['MSISDN'] == phone_number
    assert data['status'] == "5"
    assert data['reference'] == "mmg_reference"
    assert data['CID'] == "1234"


@pytest.mark.parametrize("phone_number", ["07700900003", "+447700900003", "7700900003", "+44 7700900003"])
def test_temp_failure_mmg_callback(phone_number):
    data = json.loads(mmg_callback("1234", phone_number))
    assert data['MSISDN'] == phone_number
    assert data['status'] == "4"
    assert data['reference'] == "mmg_reference"
    assert data['CID'] == "1234"


@pytest.mark.parametrize("phone_number", ["07700900001", "+447700900001", "7700900001", "+44 7700900001",
                                          "+447700900256"])
def test_delivered_firetext_callback(phone_number):
    assert firetext_callback('1234', phone_number) == {
        'mobile': phone_number,
        'status': '0',
        'time': '2016-03-10 14:17:00',
        'reference': '1234'
    }


@pytest.mark.parametrize("phone_number", ["07700900002", "+447700900002", "7700900002", "+44 7700900002"])
def test_failure_firetext_callback(phone_number):
    assert firetext_callback('1234', phone_number) == {
        'mobile': phone_number,
        'status': '1',
        'time': '2016-03-10 14:17:00',
        'reference': '1234'
    }
