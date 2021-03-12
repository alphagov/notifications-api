import uuid
from unittest.mock import ANY, call

import pytest
import requests_mock
from flask import current_app, json
from freezegun import freeze_time

from app.celery.research_mode_tasks import (
    HTTPError,
    create_fake_letter_response_file,
    firetext_callback,
    mmg_callback,
    send_email_response,
    send_sms_response,
    ses_notification_callback,
)
from app.config import QueueNames
from tests.conftest import Matcher, set_config_values

dvla_response_file_matcher = Matcher(
    'dvla_response_file',
    lambda x: 'NOTIFY-20180125140000-RSP.TXT' < x <= 'NOTIFY-20180125140030-RSP.TXT'
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


def test_callback_logs_on_api_call_failure(notify_api, rmock, mocker):
    endpoint = "http://localhost:6011/notifications/sms/mmg"
    rmock.request(
        "POST",
        endpoint,
        json={"error": "something went wrong"},
        status_code=500)
    mock_logger = mocker.patch('app.celery.tasks.current_app.logger.error')

    with pytest.raises(HTTPError):
        send_sms_response("mmg", "1234", "07700900001")

    assert rmock.called
    assert rmock.request_history[0].url == endpoint
    mock_logger.assert_called_once_with(
        'API POST request on http://localhost:6011/notifications/sms/mmg failed with status 500'
    )


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


@freeze_time("2018-01-25 14:00:30")
def test_create_fake_letter_response_file_uploads_response_file_s3(
        notify_api, mocker):
    mocker.patch('app.celery.research_mode_tasks.file_exists', return_value=False)
    mock_s3upload = mocker.patch('app.celery.research_mode_tasks.s3upload')

    with requests_mock.Mocker() as request_mock:
        request_mock.post(
            'http://localhost:6011/notifications/letter/dvla',
            content=b'{}',
            status_code=200
        )

        create_fake_letter_response_file('random-ref')

        mock_s3upload.assert_called_once_with(
            filedata='random-ref|Sent|0|Sorted',
            region=current_app.config['AWS_REGION'],
            bucket_name=current_app.config['DVLA_RESPONSE_BUCKET_NAME'],
            file_location=dvla_response_file_matcher
        )


@freeze_time("2018-01-25 14:00:30")
def test_create_fake_letter_response_file_calls_dvla_callback_on_development(
        notify_api, mocker):
    mocker.patch('app.celery.research_mode_tasks.file_exists', return_value=False)
    mocker.patch('app.celery.research_mode_tasks.s3upload')

    with set_config_values(notify_api, {
        'NOTIFY_ENVIRONMENT': 'development'
    }):
        with requests_mock.Mocker() as request_mock:
            request_mock.post(
                'http://localhost:6011/notifications/letter/dvla',
                content=b'{}',
                status_code=200
            )

            create_fake_letter_response_file('random-ref')

            assert request_mock.last_request.json() == {
                "Type": "Notification",
                "MessageId": "some-message-id",
                "Message": ANY
            }
            assert json.loads(request_mock.last_request.json()['Message']) == {
                "Records": [
                    {
                        "s3": {
                            "object": {
                                "key": dvla_response_file_matcher
                            }
                        }
                    }
                ]
            }


@freeze_time("2018-01-25 14:00:30")
def test_create_fake_letter_response_file_does_not_call_dvla_callback_on_preview(
        notify_api, mocker):
    mocker.patch('app.celery.research_mode_tasks.file_exists', return_value=False)
    mocker.patch('app.celery.research_mode_tasks.s3upload')

    with set_config_values(notify_api, {
        'NOTIFY_ENVIRONMENT': 'preview'
    }):
        with requests_mock.Mocker() as request_mock:
            create_fake_letter_response_file('random-ref')

            assert request_mock.last_request is None


@freeze_time("2018-01-25 14:00:30")
def test_create_fake_letter_response_file_tries_to_create_files_with_other_filenames(notify_api, mocker):
    mock_file_exists = mocker.patch('app.celery.research_mode_tasks.file_exists', side_effect=[True, True, False])
    mock_s3upload = mocker.patch('app.celery.research_mode_tasks.s3upload')

    create_fake_letter_response_file('random-ref')

    assert mock_file_exists.mock_calls == [
        call('test.notify.com-ftp', dvla_response_file_matcher),
        call('test.notify.com-ftp', dvla_response_file_matcher),
        call('test.notify.com-ftp', dvla_response_file_matcher),
    ]
    mock_s3upload.assert_called_once_with(
        filedata=ANY,
        region=ANY,
        bucket_name=ANY,
        file_location=dvla_response_file_matcher
    )


@freeze_time("2018-01-25 14:00:30")
def test_create_fake_letter_response_file_gives_up_after_thirty_times(notify_api, mocker):
    mock_file_exists = mocker.patch('app.celery.research_mode_tasks.file_exists', return_value=True)
    mock_s3upload = mocker.patch('app.celery.research_mode_tasks.s3upload')

    with pytest.raises(ValueError):
        create_fake_letter_response_file('random-ref')

    assert len(mock_file_exists.mock_calls) == 30
    assert not mock_s3upload.called
