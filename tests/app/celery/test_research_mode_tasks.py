import uuid
from unittest.mock import ANY

import pytest
import requests
from celery.exceptions import MaxRetriesExceededError
from flask import json
from freezegun import freeze_time

from app import signing
from app.celery.process_ses_receipts_tasks import process_ses_results
from app.celery.research_mode_tasks import (
    create_fake_letter_callback,
    firetext_callback,
    mmg_callback,
    send_email_response,
    send_sms_response,
    ses_notification_callback,
)
from app.config import QueueNames


def test_make_mmg_callback(notify_api, rmock):
    endpoint = "http://localhost:6011/notifications/sms/mmg"
    rmock.request("POST", endpoint, json={"status": "success"}, status_code=200)
    send_sms_response("mmg", "1234", "07700900001")

    assert rmock.called
    assert rmock.request_history[0].url == endpoint
    assert json.loads(rmock.request_history[0].text)["MSISDN"] == "07700900001"


def test_callback_logs_on_api_call_failure(notify_api, rmock, caplog):
    endpoint = "http://localhost:6011/notifications/sms/mmg"
    rmock.request("POST", endpoint, json={"error": "something went wrong"}, status_code=500)

    with pytest.raises(requests.HTTPError), caplog.at_level("ERROR"):
        send_sms_response("mmg", "1234", "07700900001")

    assert rmock.called
    assert rmock.request_history[0].url == endpoint
    assert "API POST request on http://localhost:6011/notifications/sms/mmg failed with status 500" in caplog.messages


@pytest.mark.parametrize("phone_number", ["07700900001", "07700900002", "07700900003", "07700900236"])
def test_make_firetext_callback(notify_api, rmock, phone_number):
    endpoint = "http://localhost:6011/notifications/sms/firetext"
    rmock.request("POST", endpoint, json="some data", status_code=200)
    send_sms_response("firetext", "1234", phone_number)

    assert rmock.called
    assert rmock.request_history[0].url == endpoint
    assert f"mobile={phone_number}" in rmock.request_history[0].text


def test_make_ses_callback(notify_api, mock_celery_task):
    mock_task = mock_celery_task(process_ses_results)
    some_ref = str(uuid.uuid4())

    send_email_response(reference=some_ref, to="test@test.com")

    mock_task.assert_called_once_with(ANY, queue=QueueNames.RESEARCH_MODE)
    assert mock_task.call_args[0][0][0] == ses_notification_callback(some_ref)


@pytest.mark.parametrize(
    "phone_number", ["07700900001", "+447700900001", "7700900001", "+44 7700900001", "+447700900236"]
)
def test_delivered_mmg_callback(phone_number):
    data = json.loads(mmg_callback("1234", phone_number))
    assert data["MSISDN"] == phone_number
    assert data["status"] == "3"
    assert data["reference"] == "mmg_reference"
    assert data["CID"] == "1234"


@pytest.mark.parametrize("phone_number", ["07700900002", "+447700900002", "7700900002", "+44 7700900002"])
def test_perm_failure_mmg_callback(phone_number):
    data = json.loads(mmg_callback("1234", phone_number))
    assert data["MSISDN"] == phone_number
    assert data["status"] == "5"
    assert data["reference"] == "mmg_reference"
    assert data["CID"] == "1234"


@pytest.mark.parametrize("phone_number", ["07700900003", "+447700900003", "7700900003", "+44 7700900003"])
def test_temp_failure_mmg_callback(phone_number):
    data = json.loads(mmg_callback("1234", phone_number))
    assert data["MSISDN"] == phone_number
    assert data["status"] == "4"
    assert data["reference"] == "mmg_reference"
    assert data["CID"] == "1234"


@pytest.mark.parametrize(
    "phone_number", ["07700900001", "+447700900001", "7700900001", "+44 7700900001", "+447700900256"]
)
def test_delivered_firetext_callback(phone_number):
    assert firetext_callback("1234", phone_number) == {
        "mobile": phone_number,
        "status": "0",
        "time": "2016-03-10 14:17:00",
        "reference": "1234",
    }


@pytest.mark.parametrize("phone_number", ["07700900002", "+447700900002", "7700900002", "+44 7700900002"])
def test_failure_firetext_callback(phone_number):
    assert firetext_callback("1234", phone_number) == {
        "mobile": phone_number,
        "status": "1",
        "time": "2016-03-10 14:17:00",
        "reference": "1234",
    }


@freeze_time("2024-07-26 16:30:53.321")
@pytest.mark.parametrize(
    "billable_units, postage, response_postage, response_mailing_product",
    [
        ("1", "first", "1ST", "UNCODED"),
        ("3", "second", "2ND", "MM"),
        ("4", "economy", "2ND", "UNSORTEDE"),
        ("5", "europe", "INTERNATIONAL", "INT EU"),
        ("2", "rest-of-world", "INTERNATIONAL", "INT ROW"),
    ],
)
def test_create_fake_letter_callback_sends_letter_response(
    notify_api,
    sample_letter_notification,
    billable_units,
    postage,
    response_postage,
    response_mailing_product,
    rmock,
):
    sample_letter_notification.billable_units = billable_units
    sample_letter_notification.postage = postage
    rmock.post(
        f"http://localhost:6011/notifications/letter/status?token={signing.encode(str(sample_letter_notification.id))}",
    )

    create_fake_letter_callback(
        sample_letter_notification.id,
        sample_letter_notification.billable_units,
        sample_letter_notification.postage,
    )

    assert rmock.last_request.headers["Content-Type"] == "application/json"
    assert rmock.last_request.json() == {
        "id": "1234",
        "source": "dvla:resource:osl:print:print-hub-fulfilment:5.18.0",
        "specVersion": "1",
        "type": "uk.gov.dvla.osl.osldatadictionaryschemas.print.messages.v2.PrintJobStatus",
        "time": "2024-04-01T00:00:00Z",
        "dataContentType": "application/json",
        "dataSchema": "https://osl-data-dictionary-schemas.engineering.dvla.gov.uk/print/messages/v2/print-job-status.json",
        "data": {
            "despatchProperties": [
                {"key": "totalSheets", "value": billable_units},
                {"key": "postageClass", "value": response_postage},
                {"key": "mailingProduct", "value": response_mailing_product},
                {"key": "productionRunDate", "value": "2024-07-26 16:30:53.321000"},
            ],
            "jobId": str(sample_letter_notification.id),
            "jobType": "NOTIFY",
            "jobStatus": "DESPATCHED",
            "templateReference": "NOTIFY",
            "transitionDate": "2024-07-26T16:30:53Z",
        },
        "metadata": {
            "handler": {"urn": "dvla:resource:osl:print:print-hub-fulfilment:5.18.0"},
            "origin": {"urn": "dvla:resource:osg:dev:printhub:1.0.1"},
            "correlationId": "b5d9b2bd-6e8f-4275-bdd3-c8086fe09c52",
        },
    }


def test_create_fake_letter_callback_retries(notify_api, fake_uuid, mocker):
    mocker.patch("app.celery.research_mode_tasks.send_letter_response", side_effect=requests.HTTPError())
    mock_retry = mocker.patch("app.celery.research_mode_tasks.create_fake_letter_callback.retry")

    create_fake_letter_callback(uuid.UUID(fake_uuid), 2, "second")

    assert mock_retry.called


def test_create_fake_letter_callback_logs_if_max_retries_exceeded(notify_api, fake_uuid, caplog, mocker):
    mocker.patch("app.celery.research_mode_tasks.send_letter_response", side_effect=requests.HTTPError())
    mocker.patch(
        "app.celery.research_mode_tasks.create_fake_letter_callback.retry", side_effect=MaxRetriesExceededError()
    )

    with caplog.at_level("WARN"):
        create_fake_letter_callback(uuid.UUID(fake_uuid), 2, "second")

    assert f"Fake letter callback cound not be created for {fake_uuid}" in caplog.messages
