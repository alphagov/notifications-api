from flask import json

from app.celery.process_sms_client_response_tasks import process_sms_client_response
from app.notifications.notifications_sms_callback import validate_callback_data


def firetext_post(client, data):
    return client.post(
        path="/notifications/sms/firetext", data=data, headers=[("Content-Type", "application/x-www-form-urlencoded")]
    )


def mmg_post(client, data):
    return client.post(path="/notifications/sms/mmg", data=data, headers=[("Content-Type", "application/json")])


def test_firetext_callback_should_not_need_auth(client, mocker):
    mocker.patch("app.notifications.notifications_sms_callback.process_sms_client_response")
    data = "mobile=441234123123&status=0&reference=notification_id&time=2016-03-10 14:17:00"

    response = firetext_post(client, data)
    assert response.status_code == 200


def test_firetext_callback_should_return_400_if_empty_reference(client):
    data = "mobile=441234123123&status=0&reference=&time=2016-03-10 14:17:00"
    response = firetext_post(client, data)

    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 400
    assert json_resp["result"] == "error"
    assert json_resp["message"] == ["Firetext callback failed: reference missing"]


def test_firetext_callback_should_return_400_if_no_reference(client):
    data = "mobile=441234123123&status=0&time=2016-03-10 14:17:00"
    response = firetext_post(client, data)
    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 400
    assert json_resp["result"] == "error"
    assert json_resp["message"] == ["Firetext callback failed: reference missing"]


def test_firetext_callback_should_return_400_if_no_status(client):
    data = "mobile=441234123123&time=2016-03-10 14:17:00&reference=notification_id"
    response = firetext_post(client, data)
    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 400
    assert json_resp["result"] == "error"
    assert json_resp["message"] == ["Firetext callback failed: status missing"]


def test_firetext_callback_should_return_200_and_call_task_with_valid_data(client, mock_celery_task):
    mock_celery = mock_celery_task(process_sms_client_response)

    data = "mobile=441234123123&status=0&time=2016-03-10 14:17:00&reference=notification_id"
    response = firetext_post(client, data)
    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 200
    assert json_resp["result"] == "success"

    mock_celery.assert_called_once_with(
        ["0", "notification_id", "Firetext", None],
        queue="sms-callbacks",
    )


def test_firetext_callback_including_a_code_should_return_200_and_call_task_with_valid_data(client, mock_celery_task):
    mock_celery = mock_celery_task(process_sms_client_response)

    data = "mobile=441234123123&status=1&code=101&time=2016-03-10 14:17:00&reference=notification_id"
    response = firetext_post(client, data)
    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 200
    assert json_resp["result"] == "success"

    mock_celery.assert_called_once_with(
        ["1", "notification_id", "Firetext", "101"],
        queue="sms-callbacks",
    )


def test_mmg_callback_should_not_need_auth(client, mocker, sample_notification):
    mocker.patch("app.notifications.notifications_sms_callback.process_sms_client_response")
    data = json.dumps(
        {
            "reference": "mmg_reference",
            "CID": str(sample_notification.id),
            "MSISDN": "447777349060",
            "status": "3",
            "deliverytime": "2016-04-05 16:01:07",
        }
    )

    response = mmg_post(client, data)
    assert response.status_code == 200


def test_process_mmg_response_returns_400_for_malformed_data(client):
    data = json.dumps(
        {
            "reference": "mmg_reference",
            "monkey": "random thing",
            "MSISDN": "447777349060",
            "no_status": 00,
            "deliverytime": "2016-04-05 16:01:07",
        }
    )

    response = mmg_post(client, data)
    assert response.status_code == 400
    json_data = json.loads(response.data)
    assert json_data["result"] == "error"
    assert len(json_data["message"]) == 2
    assert "{} callback failed: {} missing".format("MMG", "status") in json_data["message"]
    assert "{} callback failed: {} missing".format("MMG", "CID") in json_data["message"]


def test_mmg_callback_should_return_200_and_call_task_with_valid_data(client, mock_celery_task):
    mock_celery = mock_celery_task(process_sms_client_response)
    data = json.dumps(
        {
            "reference": "mmg_reference",
            "CID": "notification_id",
            "MSISDN": "447777349060",
            "status": "3",
            "substatus": "5",
            "deliverytime": "2016-04-05 16:01:07",
        }
    )

    response = mmg_post(client, data)

    assert response.status_code == 200
    json_data = json.loads(response.data)
    assert json_data["result"] == "success"

    mock_celery.assert_called_once_with(
        ["3", "notification_id", "MMG", "5"],
        queue="sms-callbacks",
    )


def test_validate_callback_data_returns_none_when_valid():
    form = {"status": "good", "reference": "send-sms-code"}
    fields = ["status", "reference"]
    client_name = "sms client"

    assert validate_callback_data(form, fields, client_name) is None


def test_validate_callback_data_return_errors_when_fields_are_empty():
    form = {"monkey": "good"}
    fields = ["status", "cid"]
    client_name = "sms client"

    errors = validate_callback_data(form, fields, client_name)
    assert len(errors) == 2
    assert "{} callback failed: {} missing".format(client_name, "status") in errors
    assert "{} callback failed: {} missing".format(client_name, "cid") in errors


def test_validate_callback_data_can_handle_integers():
    form = {"status": 00, "cid": "fsdfadfsdfas"}
    fields = ["status", "cid"]
    client_name = "sms client"

    result = validate_callback_data(form, fields, client_name)
    assert result is None


def test_validate_callback_data_returns_error_for_empty_string():
    form = {"status": "", "cid": "fsdfadfsdfas"}
    fields = ["status", "cid"]
    client_name = "sms client"

    result = validate_callback_data(form, fields, client_name)
    assert result is not None
    assert "{} callback failed: {} missing".format(client_name, "status") in result
