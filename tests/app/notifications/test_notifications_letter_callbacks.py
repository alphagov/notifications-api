import datetime
import uuid

import pytest
from flask import json, url_for
from itsdangerous import BadSignature

from app import signing
from app.celery.process_letter_client_response_tasks import process_letter_callback_data
from app.errors import InvalidRequest
from app.models import LetterCostThreshold
from app.notifications.notifications_letter_callback import (
    _get_cost_threshold,
    _get_despatch_date,
    check_token_matches_payload,
    extract_properties_from_request,
    parse_token,
)


@pytest.mark.parametrize("token", [None, "invalid-token"])
def test_process_letter_callback_gives_error_for_missing_or_invalid_token(client, token, mock_dvla_callback_data):
    # assert that even with invalid json, we still check the token first
    data = json.dumps(mock_dvla_callback_data(overrides={"id": None}))
    response = client.post(
        url_for("notifications_letter_callback.process_letter_callback", token=token),
        data=data,
        headers=[("Content-Type", "application/json")],
    )

    assert response.status_code == 403
    assert response.get_json()["errors"][0]["message"] == "A valid token must be provided in the query string"


@pytest.mark.parametrize(
    "overrides, expected_error_message",
    [
        # missing `id`
        (
            {"id": None},
            "id is a required property",
        ),
        # missing `time`
        (
            {"time": None},
            "time is a required property",
        ),
        # missing `data`
        (
            {"data": None},
            "data is a required property",
        ),
        # missing `metadata`
        (
            {"metadata": None},
            "metadata is a required property",
        ),
        # missing `jobId` in data
        (
            {"data": {"jobId": None}},
            "jobId is a required property",
        ),
        # missing `jobStatus` in data
        (
            {"data": {"jobStatus": None}},
            "jobStatus is a required property",
        ),
        # missing `correlationId` in metadata
        (
            {"metadata": {"correlationId": None}},
            "correlationId is a required property",
        ),
        # invalid enum value for `jobStatus`
        (
            {"data": {"jobStatus": "INVALID_STATUS"}},
            "data INVALID_STATUS is not one of [DESPATCHED, REJECTED]",
        ),
        # invalid `time` format
        (
            {"time": "invalid-time-format"},
            "time invalid-time-format is not a date-time",
        ),
        # invalid `jobId` format
        (
            {"data": {"jobId": "1234 not a uuid 1234"}},
            "data badly formed hexadecimal UUID string",
        ),
        # missing `transitionDate` in data
        (
            {"data": {"transitionDate": None}},
            "data transitionDate is a required property",
        ),
        # invalid `transitionDate` in format
        (
            {"data": {"transitionDate": "2025-03-31T13:15Z"}},
            "data 2025-03-31T13:15Z is not a date-time",
        ),
    ],
)
def test_process_letter_callback_validation_for_required_fields(
    client, mock_dvla_callback_data, overrides, expected_error_message
):
    data = mock_dvla_callback_data(overrides=overrides)

    response = client.post(
        url_for(
            "notifications_letter_callback.process_letter_callback",
            token=signing.encode("cfce9e7b-1534-4c07-a66d-3cf9172f7640"),
        ),
        data=json.dumps(data),
    )

    response_json_data = response.get_json()
    errors = response_json_data["errors"]

    assert response.status_code == 400
    assert any(expected_error_message in error["message"] for error in errors), (
        f"Expected error message '{expected_error_message}' not found in {errors}"
    )


@pytest.mark.parametrize(
    "despatch_properties, expected_error_message",
    [
        # invalid enum for postageClass
        (
            [
                {"key": "postageClass", "value": "invalid-postage-class"},
                {"key": "totalSheets", "value": "5"},
                {"key": "mailingProduct", "value": "MM UNSORTED"},
            ],
            "data {key: postageClass, value: invalid-postage-class} is not valid under any of the given schemas",
        ),
        # invalid enum for mailingProduct
        (
            [
                {"key": "postageClass", "value": "1ST"},
                {"key": "totalSheets", "value": "5"},
                {"key": "mailingProduct", "value": "invalid-mailing-product"},
            ],
            "data {key: mailingProduct, value: invalid-mailing-product} is not valid under any of the given schemas",
        ),
    ],
)
def test_process_letter_callback_validation_for_despatch_properties(
    client, mock_dvla_callback_data, despatch_properties, expected_error_message
):
    data = mock_dvla_callback_data(overrides={"data": {"despatchProperties": despatch_properties}})
    response = client.post(
        url_for(
            "notifications_letter_callback.process_letter_callback",
            token=signing.encode("cfce9e7b-1534-4c07-a66d-3cf9172f7640"),
        ),
        data=json.dumps(data),
    )

    response_json_data = response.get_json()
    errors = response_json_data["errors"]

    assert response.status_code == 400
    assert any(expected_error_message in error["message"] for error in errors), (
        f"Expected error message '{expected_error_message}' not found in {errors}"
    )


def test_process_letter_callback_raises_error_if_token_and_notification_id_in_data_do_not_match(
    client,
    caplog,
    mock_dvla_callback_data,
    fake_uuid,
):
    signed_token_id = signing.encode(fake_uuid)

    data = mock_dvla_callback_data()

    response = client.post(
        url_for("notifications_letter_callback.process_letter_callback", token=signed_token_id),
        data=json.dumps(data),
    )

    assert response.status_code == 400
    assert response.get_json()["errors"][0]["message"] == (
        "Notification ID in letter callback data does not match ID in token"
    )


@pytest.mark.parametrize(
    "status,transition_date,expected_month,expected_day",
    [("DESPATCHED", "2025-04-01T23:30:07Z", 4, 2), ("REJECTED", "2025-02-01T23:30:07Z", 2, 1)],
)
def test_process_letter_callback_calls_process_letter_callback_data_task(
    client, mock_celery_task, mock_dvla_callback_data, status, transition_date, expected_month, expected_day
):
    mock_task = mock_celery_task(process_letter_callback_data)
    data = mock_dvla_callback_data()
    data["data"]["jobStatus"] = status
    data["data"]["transitionDate"] = transition_date

    response = client.post(
        url_for(
            "notifications_letter_callback.process_letter_callback",
            token=signing.encode("cfce9e7b-1534-4c07-a66d-3cf9172f7640"),
        ),
        data=json.dumps(data),
    )

    assert response.status_code == 204, response.json

    mock_task.assert_called_once_with(
        queue="letter-callbacks",
        kwargs={
            "notification_id": uuid.UUID("cfce9e7b-1534-4c07-a66d-3cf9172f7640"),
            "page_count": 5,
            "dvla_status": status,
            "cost_threshold": LetterCostThreshold.unsorted,
            "despatch_date": datetime.date(2025, expected_month, expected_day),
        },
    )


@pytest.mark.parametrize("token", [None, "invalid-token"])
def test_parse_token_invalid(client, token, caplog, mocker):
    mocker.patch("app.signing.decode", side_effect=BadSignature("Invalid token"))

    with pytest.raises(InvalidRequest) as e:
        parse_token(token)

    assert f"Letter callback with invalid token of {token} received" in caplog.text
    assert "A valid token must be provided in the query string" in str(e.value)


def test_check_token_fails_invalid_payload(caplog, client):
    with pytest.raises(InvalidRequest):
        check_token_matches_payload(token_id="12345", json_id="67890")

    assert "Notification ID in token does not match json. token: 12345 - json: 67890" in caplog.messages


def test_check_token_passes_matching_paylods(caplog, client):
    check_token_matches_payload(token_id="12345", json_id="12345")
    assert not caplog.records, "Expected no log messages, but some were captured."


def test_extract_properties_from_request(mock_dvla_callback_data):
    overrides = {
        "data": {
            "despatchProperties": [
                {"key": "totalSheets", "value": "10"},
                {"key": "postageClass", "value": "1ST"},
                {"key": "mailingProduct", "value": "MM UNSORTED"},
            ],
            "jobStatus": "REJECTED",
            "transitionDate": "2025-03-31T13:15:07Z",
        }
    }

    data = mock_dvla_callback_data(overrides)

    letter_update = extract_properties_from_request(data)

    assert letter_update.page_count == 10
    assert letter_update.status == "REJECTED"
    assert letter_update.cost_threshold == LetterCostThreshold.unsorted
    assert letter_update.despatch_date == datetime.date(2025, 3, 31)


@pytest.mark.parametrize("postage", ["1ST", "2ND", "INTERNATIONAL"])
@pytest.mark.parametrize("mailing_product", ["UNCODED", "MM UNSORTED", "UNSORTED", "MM", "INT EU", "INT ROW"])
def test__get_cost_threshold(mailing_product, postage):
    if postage == "2ND" and mailing_product == "MM":
        expected_cost_threshold = LetterCostThreshold.sorted
    else:
        expected_cost_threshold = LetterCostThreshold.unsorted

    assert _get_cost_threshold(mailing_product, postage) == expected_cost_threshold


@pytest.mark.parametrize(
    "datestring, expected_result",
    [
        ("2024-08-01 09:15:14.456", datetime.date(2024, 8, 1)),
        ("2024-08-01 23:15:14.000", datetime.date(2024, 8, 1)),
        ("2024-01-21 23:15:14.000", datetime.date(2024, 1, 21)),
    ],
)
def test__get_despatch_date(datestring, expected_result):
    assert _get_despatch_date(datestring) == expected_result
