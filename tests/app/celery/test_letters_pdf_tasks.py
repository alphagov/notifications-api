from unittest.mock import Mock, call, ANY

import boto3
from PyPDF2.utils import PdfReadError
from moto import mock_s3
from flask import current_app
from freezegun import freeze_time
import pytest
import requests_mock
from botocore.exceptions import ClientError
from celery.exceptions import MaxRetriesExceededError, Retry
from requests import RequestException
from sqlalchemy.orm.exc import NoResultFound

from app.errors import VirusScanError
from app.celery.letters_pdf_tasks import (
    create_letters_pdf,
    get_letters_pdf,
    collate_letter_pdfs_for_day,
    group_letters,
    letter_in_created_state,
    process_virus_scan_passed,
    process_virus_scan_failed,
    process_virus_scan_error,
    replay_letters_in_error,
    _sanitise_precompiled_pdf
)
from app.letters.utils import get_letter_pdf_filename, ScanErrorType
from app.models import (
    KEY_TYPE_NORMAL,
    KEY_TYPE_TEST,
    Notification,
    NOTIFICATION_CREATED,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_PENDING_VIRUS_CHECK,
    NOTIFICATION_SENDING,
    NOTIFICATION_TECHNICAL_FAILURE,
    NOTIFICATION_VALIDATION_FAILED,
    NOTIFICATION_VIRUS_SCAN_FAILED,
)

from tests.app.db import create_notification, create_letter_branding

from tests.conftest import set_config_values


def test_should_have_decorated_tasks_functions():
    assert create_letters_pdf.__wrapped__.__name__ == 'create_letters_pdf'


@pytest.mark.parametrize('personalisation', [{'name': 'test'}, None])
def test_get_letters_pdf_calls_notifications_template_preview_service_correctly(
        notify_api, mocker, client, sample_letter_template, personalisation):
    contact_block = 'Mr Foo,\n1 Test Street,\nLondon\nN1'
    filename = 'opg'

    with set_config_values(notify_api, {
        'TEMPLATE_PREVIEW_API_HOST': 'http://localhost/notifications-template-preview',
        'TEMPLATE_PREVIEW_API_KEY': 'test-key'
    }):
        with requests_mock.Mocker() as request_mock:
            mock_post = request_mock.post(
                'http://localhost/notifications-template-preview/print.pdf', content=b'\x00\x01', status_code=200)

            get_letters_pdf(
                sample_letter_template,
                contact_block=contact_block,
                filename=filename,
                values=personalisation)

    assert mock_post.last_request.json() == {
        'values': personalisation,
        'letter_contact_block': contact_block,
        'filename': filename,
        'template': {
            'subject': sample_letter_template.subject,
            'content': sample_letter_template.content
        }
    }


@pytest.mark.parametrize('page_count,expected_billable_units', [
    ('1', 1),
    ('2', 1),
    ('3', 2)
])
def test_get_letters_pdf_calculates_billing_units(
        notify_api, mocker, client, sample_letter_template, page_count, expected_billable_units):
    contact_block = 'Mr Foo,\n1 Test Street,\nLondon\nN1'
    filename = 'opg'

    with set_config_values(notify_api, {
        'TEMPLATE_PREVIEW_API_HOST': 'http://localhost/notifications-template-preview',
        'TEMPLATE_PREVIEW_API_KEY': 'test-key'
    }):
        with requests_mock.Mocker() as request_mock:
            request_mock.post(
                'http://localhost/notifications-template-preview/print.pdf',
                content=b'\x00\x01',
                headers={'X-pdf-page-count': page_count},
                status_code=200
            )

            _, billable_units = get_letters_pdf(
                sample_letter_template, contact_block=contact_block, filename=filename, values=None)

    assert billable_units == expected_billable_units


@freeze_time("2017-12-04 17:31:00")
def test_create_letters_pdf_calls_s3upload(mocker, sample_letter_notification):
    mocker.patch('app.celery.letters_pdf_tasks.get_letters_pdf', return_value=(b'\x00\x01', '1'))
    mock_s3 = mocker.patch('app.letters.utils.s3upload')

    create_letters_pdf(sample_letter_notification.id)

    filename = get_letter_pdf_filename(
        reference=sample_letter_notification.reference,
        crown=sample_letter_notification.service.crown
    )

    mock_s3.assert_called_with(
        bucket_name=current_app.config['LETTERS_PDF_BUCKET_NAME'],
        file_location=filename,
        filedata=b'\x00\x01',
        region=current_app.config['AWS_REGION']
    )


def test_create_letters_pdf_sets_billable_units(mocker, sample_letter_notification):
    mocker.patch('app.celery.letters_pdf_tasks.get_letters_pdf', return_value=(b'\x00\x01', 1))
    mocker.patch('app.letters.utils.s3upload')

    create_letters_pdf(sample_letter_notification.id)
    noti = Notification.query.filter(Notification.reference == sample_letter_notification.reference).one()
    assert noti.billable_units == 1


def test_create_letters_pdf_non_existent_notification(notify_api, mocker, fake_uuid):
    with pytest.raises(expected_exception=NoResultFound):
        create_letters_pdf(fake_uuid)


def test_create_letters_pdf_handles_request_errors(mocker, sample_letter_notification):
    mock_get_letters_pdf = mocker.patch('app.celery.letters_pdf_tasks.get_letters_pdf', side_effect=RequestException)
    mock_retry = mocker.patch('app.celery.letters_pdf_tasks.create_letters_pdf.retry')

    create_letters_pdf(sample_letter_notification.id)

    assert mock_get_letters_pdf.called
    assert mock_retry.called


def test_create_letters_pdf_handles_s3_errors(mocker, sample_letter_notification):
    mocker.patch('app.celery.letters_pdf_tasks.get_letters_pdf', return_value=(b'\x00\x01', 1))
    error_response = {
        'Error': {
            'Code': 'InvalidParameterValue',
            'Message': 'some error message from amazon',
            'Type': 'Sender'
        }
    }
    mock_s3 = mocker.patch('app.letters.utils.s3upload', side_effect=ClientError(error_response, 'operation_name'))
    mock_retry = mocker.patch('app.celery.letters_pdf_tasks.create_letters_pdf.retry')

    create_letters_pdf(sample_letter_notification.id)

    assert mock_s3.called
    assert mock_retry.called


def test_create_letters_pdf_sets_technical_failure_max_retries(mocker, sample_letter_notification):
    mock_get_letters_pdf = mocker.patch('app.celery.letters_pdf_tasks.get_letters_pdf', side_effect=RequestException)
    mock_retry = mocker.patch(
        'app.celery.letters_pdf_tasks.create_letters_pdf.retry', side_effect=MaxRetriesExceededError)
    mock_update_noti = mocker.patch('app.celery.letters_pdf_tasks.update_notification_status_by_id')

    create_letters_pdf(sample_letter_notification.id)

    assert mock_get_letters_pdf.called
    assert mock_retry.called
    mock_update_noti.assert_called_once_with(sample_letter_notification.id, 'technical-failure')


# We only need this while we are migrating to the new letter_branding model
def test_create_letters_gets_the_right_logo_when_service_has_dvla_logo(
        notify_api, mocker, sample_letter_notification
):
    mock_get_letters_pdf = mocker.patch('app.celery.letters_pdf_tasks.get_letters_pdf', return_value=(b'\x00\x01', 1))
    mocker.patch('app.letters.utils.s3upload')
    mocker.patch('app.celery.letters_pdf_tasks.update_notification_status_by_id')

    create_letters_pdf(sample_letter_notification.id)
    mock_get_letters_pdf.assert_called_once_with(
        sample_letter_notification.template,
        contact_block=sample_letter_notification.reply_to_text,
        filename=sample_letter_notification.service.dvla_organisation.filename,
        values=sample_letter_notification.personalisation
    )


# We only need this while we are migrating to the new letter_branding model
def test_create_letters_gets_the_right_logo_when_service_has_letter_branding_logo(
        notify_api, mocker, sample_letter_notification
):
    letter_branding = create_letter_branding(name='test brand', filename='test-brand')
    sample_letter_notification.service.letter_branding = letter_branding
    mock_get_letters_pdf = mocker.patch('app.celery.letters_pdf_tasks.get_letters_pdf', return_value=(b'\x00\x01', 1))
    mocker.patch('app.letters.utils.s3upload')
    mocker.patch('app.celery.letters_pdf_tasks.update_notification_status_by_id')

    create_letters_pdf(sample_letter_notification.id)
    mock_get_letters_pdf.assert_called_once_with(
        sample_letter_notification.template,
        contact_block=sample_letter_notification.reply_to_text,
        filename=sample_letter_notification.service.letter_branding.filename,
        values=sample_letter_notification.personalisation
    )


def test_collate_letter_pdfs_for_day(notify_api, mocker):
    mock_s3 = mocker.patch('app.celery.tasks.s3.get_s3_bucket_objects')
    mock_group_letters = mocker.patch('app.celery.letters_pdf_tasks.group_letters', return_value=[
        [{'Key': 'A.PDF', 'Size': 1}, {'Key': 'B.pDf', 'Size': 2}],
        [{'Key': 'C.pdf', 'Size': 3}]
    ])
    mock_celery = mocker.patch('app.celery.letters_pdf_tasks.notify_celery.send_task')

    collate_letter_pdfs_for_day('2017-01-02')

    mock_s3.assert_called_once_with('test-letters-pdf', subfolder='2017-01-02')
    mock_group_letters.assert_called_once_with(mock_s3.return_value)
    assert mock_celery.call_args_list[0] == call(
        name='zip-and-send-letter-pdfs',
        kwargs={'filenames_to_zip': ['A.PDF', 'B.pDf']},
        queue='process-ftp-tasks',
        compression='zlib'
    )
    assert mock_celery.call_args_list[1] == call(
        name='zip-and-send-letter-pdfs',
        kwargs={'filenames_to_zip': ['C.pdf']},
        queue='process-ftp-tasks',
        compression='zlib'
    )


@freeze_time('2018-09-12 17:50:00')
def test_collate_letter_pdfs_for_day_works_without_date_param(notify_api, mocker):
    mock_s3 = mocker.patch('app.celery.tasks.s3.get_s3_bucket_objects')
    collate_letter_pdfs_for_day()
    expected_date = '2018-09-12'
    mock_s3.assert_called_once_with('test-letters-pdf', subfolder=expected_date)


def test_group_letters_splits_on_file_size(notify_api, mocker):
    mocker.patch('app.celery.letters_pdf_tasks.letter_in_created_state', return_value=True)
    letters = [
        # ends under max but next one is too big
        {'Key': 'A.pdf', 'Size': 1}, {'Key': 'B.pdf', 'Size': 2},
        # ends on exactly max
        {'Key': 'C.pdf', 'Size': 3}, {'Key': 'D.pdf', 'Size': 1}, {'Key': 'E.pdf', 'Size': 1},
        # exactly max goes in next file
        {'Key': 'F.pdf', 'Size': 5},
        # if it's bigger than the max, still gets included
        {'Key': 'G.pdf', 'Size': 6},
        # whatever's left goes in last list
        {'Key': 'H.pdf', 'Size': 1}, {'Key': 'I.pdf', 'Size': 1},
    ]

    with set_config_values(notify_api, {'MAX_LETTER_PDF_ZIP_FILESIZE': 5}):
        x = group_letters(letters)

        assert next(x) == [{'Key': 'A.pdf', 'Size': 1}, {'Key': 'B.pdf', 'Size': 2}]
        assert next(x) == [{'Key': 'C.pdf', 'Size': 3}, {'Key': 'D.pdf', 'Size': 1}, {'Key': 'E.pdf', 'Size': 1}]
        assert next(x) == [{'Key': 'F.pdf', 'Size': 5}]
        assert next(x) == [{'Key': 'G.pdf', 'Size': 6}]
        assert next(x) == [{'Key': 'H.pdf', 'Size': 1}, {'Key': 'I.pdf', 'Size': 1}]
        # make sure iterator is exhausted
        assert next(x, None) is None


def test_group_letters_splits_on_file_count(notify_api, mocker):
    mocker.patch('app.celery.letters_pdf_tasks.letter_in_created_state', return_value=True)
    letters = [
        {'Key': 'A.pdf', 'Size': 1},
        {'Key': 'B.pdf', 'Size': 2},
        {'Key': 'C.pdf', 'Size': 3},
        {'Key': 'D.pdf', 'Size': 1},
        {'Key': 'E.pdf', 'Size': 1},
        {'Key': 'F.pdf', 'Size': 5},
        {'Key': 'G.pdf', 'Size': 6},
        {'Key': 'H.pdf', 'Size': 1},
        {'Key': 'I.pdf', 'Size': 1},
    ]

    with set_config_values(notify_api, {'MAX_LETTER_PDF_COUNT_PER_ZIP': 3}):
        x = group_letters(letters)

        assert next(x) == [{'Key': 'A.pdf', 'Size': 1}, {'Key': 'B.pdf', 'Size': 2}, {'Key': 'C.pdf', 'Size': 3}]
        assert next(x) == [{'Key': 'D.pdf', 'Size': 1}, {'Key': 'E.pdf', 'Size': 1}, {'Key': 'F.pdf', 'Size': 5}]
        assert next(x) == [{'Key': 'G.pdf', 'Size': 6}, {'Key': 'H.pdf', 'Size': 1}, {'Key': 'I.pdf', 'Size': 1}]
        # make sure iterator is exhausted
        assert next(x, None) is None


def test_group_letters_splits_on_file_size_and_file_count(notify_api, mocker):
    mocker.patch('app.celery.letters_pdf_tasks.letter_in_created_state', return_value=True)
    letters = [
        # ends under max file size but next file is too big
        {'Key': 'A.pdf', 'Size': 1},
        {'Key': 'B.pdf', 'Size': 2},
        # ends on exactly max number of files and file size
        {'Key': 'C.pdf', 'Size': 3},
        {'Key': 'D.pdf', 'Size': 1},
        {'Key': 'E.pdf', 'Size': 1},
        # exactly max file size goes in next file
        {'Key': 'F.pdf', 'Size': 5},
        # file size is within max but number of files reaches limit
        {'Key': 'G.pdf', 'Size': 1},
        {'Key': 'H.pdf', 'Size': 1},
        {'Key': 'I.pdf', 'Size': 1},
        # whatever's left goes in last list
        {'Key': 'J.pdf', 'Size': 1},
    ]

    with set_config_values(notify_api, {
        'MAX_LETTER_PDF_ZIP_FILESIZE': 5,
        'MAX_LETTER_PDF_COUNT_PER_ZIP': 3
    }):
        x = group_letters(letters)

        assert next(x) == [{'Key': 'A.pdf', 'Size': 1}, {'Key': 'B.pdf', 'Size': 2}]
        assert next(x) == [{'Key': 'C.pdf', 'Size': 3}, {'Key': 'D.pdf', 'Size': 1}, {'Key': 'E.pdf', 'Size': 1}]
        assert next(x) == [{'Key': 'F.pdf', 'Size': 5}]
        assert next(x) == [{'Key': 'G.pdf', 'Size': 1}, {'Key': 'H.pdf', 'Size': 1}, {'Key': 'I.pdf', 'Size': 1}]
        assert next(x) == [{'Key': 'J.pdf', 'Size': 1}]
        # make sure iterator is exhausted
        assert next(x, None) is None


def test_group_letters_ignores_non_pdfs(notify_api, mocker):
    mocker.patch('app.celery.letters_pdf_tasks.letter_in_created_state', return_value=True)
    letters = [{'Key': 'A.zip'}]
    assert list(group_letters(letters)) == []


def test_group_letters_ignores_notifications_already_sent(notify_api, mocker):
    mock = mocker.patch('app.celery.letters_pdf_tasks.letter_in_created_state', return_value=False)
    letters = [{'Key': 'A.pdf'}]
    assert list(group_letters(letters)) == []
    mock.assert_called_once_with('A.pdf')


def test_group_letters_with_no_letters(notify_api, mocker):
    mocker.patch('app.celery.letters_pdf_tasks.letter_in_created_state', return_value=True)
    assert list(group_letters([])) == []


def test_letter_in_created_state(sample_notification):
    sample_notification.reference = 'ABCDEF1234567890'
    filename = '2018-01-13/NOTIFY.ABCDEF1234567890.D.2.C.C.20180113120000.PDF'

    assert letter_in_created_state(filename) is True


def test_letter_in_created_state_fails_if_notification_not_in_created(sample_notification):
    sample_notification.reference = 'ABCDEF1234567890'
    sample_notification.status = NOTIFICATION_SENDING
    filename = '2018-01-13/NOTIFY.ABCDEF1234567890.D.2.C.C.20180113120000.PDF'
    assert letter_in_created_state(filename) is False


def test_letter_in_created_state_fails_if_notification_doesnt_exist(sample_notification):
    sample_notification.reference = 'QWERTY1234567890'
    filename = '2018-01-13/NOTIFY.ABCDEF1234567890.D.2.C.C.20180113120000.PDF'
    assert letter_in_created_state(filename) is False


@freeze_time('2018-01-01 18:00')
@mock_s3
@pytest.mark.parametrize('key_type,noti_status,bucket_config_name,destination_folder', [
    (KEY_TYPE_NORMAL, NOTIFICATION_CREATED, 'LETTERS_PDF_BUCKET_NAME', '2018-01-02/'),
    (KEY_TYPE_TEST, NOTIFICATION_DELIVERED, 'TEST_LETTERS_BUCKET_NAME', '')
])
def test_process_letter_task_check_virus_scan_passed(
    sample_letter_template, mocker, key_type, noti_status, bucket_config_name, destination_folder
):
    letter_notification = create_notification(template=sample_letter_template, billable_units=0,
                                              status='pending-virus-check', key_type=key_type,
                                              reference='{} letter'.format(key_type))
    filename = 'NOTIFY.{}'.format(letter_notification.reference)
    source_bucket_name = current_app.config['LETTERS_SCAN_BUCKET_NAME']
    target_bucket_name = current_app.config[bucket_config_name]

    conn = boto3.resource('s3', region_name='eu-west-1')
    conn.create_bucket(Bucket=source_bucket_name)
    conn.create_bucket(Bucket=target_bucket_name)

    s3 = boto3.client('s3', region_name='eu-west-1')
    s3.put_object(Bucket=source_bucket_name, Key=filename, Body=b'pdf_content')

    mock_get_page_count = mocker.patch('app.celery.letters_pdf_tasks._get_page_count', return_value=1)
    mock_s3upload = mocker.patch('app.celery.letters_pdf_tasks.s3upload')
    mock_sanitise = mocker.patch('app.celery.letters_pdf_tasks._sanitise_precompiled_pdf', return_value=b'pdf_content')

    process_virus_scan_passed(filename)

    assert letter_notification.status == noti_status
    assert letter_notification.billable_units == 1
    mock_sanitise.assert_called_once_with(
        ANY,
        letter_notification,
        b'pdf_content'
    )
    mock_s3upload.assert_called_once_with(
        bucket_name=target_bucket_name,
        filedata=b'pdf_content',
        file_location=destination_folder + filename,
        region='eu-west-1',
    )
    mock_get_page_count.assert_called_once_with(
        letter_notification,
        b'pdf_content'
    )


@freeze_time('2018-01-01 18:00')
@mock_s3
@pytest.mark.parametrize('key_type,is_test_letter', [
    (KEY_TYPE_NORMAL, False), (KEY_TYPE_TEST, True)
])
def test_process_letter_task_check_virus_scan_passed_when_sanitise_fails(
    sample_letter_notification, mocker, key_type, is_test_letter
):
    filename = 'NOTIFY.{}'.format(sample_letter_notification.reference)
    source_bucket_name = current_app.config['LETTERS_SCAN_BUCKET_NAME']
    target_bucket_name = current_app.config['INVALID_PDF_BUCKET_NAME']

    conn = boto3.resource('s3', region_name='eu-west-1')
    conn.create_bucket(Bucket=source_bucket_name)
    conn.create_bucket(Bucket=target_bucket_name)

    s3 = boto3.client('s3', region_name='eu-west-1')
    s3.put_object(Bucket=source_bucket_name, Key=filename, Body=b'pdf_content')

    sample_letter_notification.status = NOTIFICATION_PENDING_VIRUS_CHECK
    sample_letter_notification.key_type = key_type
    mock_move_s3 = mocker.patch('app.letters.utils._move_s3_object')
    mock_sanitise = mocker.patch('app.celery.letters_pdf_tasks._sanitise_precompiled_pdf', return_value=None)
    mock_get_page_count = mocker.patch('app.celery.letters_pdf_tasks._get_page_count', return_value=2)

    process_virus_scan_passed(filename)

    assert sample_letter_notification.status == NOTIFICATION_VALIDATION_FAILED
    assert sample_letter_notification.billable_units == 0
    mock_sanitise.assert_called_once_with(
        ANY,
        sample_letter_notification,
        b'pdf_content'
    )
    mock_move_s3.assert_called_once_with(
        source_bucket_name, filename,
        target_bucket_name, filename
    )

    mock_get_page_count.assert_called_once_with(
        sample_letter_notification, b'pdf_content'
    )


@freeze_time('2018-01-01 18:00')
@mock_s3
@pytest.mark.parametrize('key_type,is_test_letter', [
    (KEY_TYPE_NORMAL, False), (KEY_TYPE_TEST, True)
])
def test_process_letter_task_check_virus_scan_passed_when_file_cannot_be_opened(
    sample_letter_notification, mocker, key_type, is_test_letter
):
    filename = 'NOTIFY.{}'.format(sample_letter_notification.reference)
    source_bucket_name = current_app.config['LETTERS_SCAN_BUCKET_NAME']
    target_bucket_name = current_app.config['INVALID_PDF_BUCKET_NAME']

    conn = boto3.resource('s3', region_name='eu-west-1')
    conn.create_bucket(Bucket=source_bucket_name)
    conn.create_bucket(Bucket=target_bucket_name)

    s3 = boto3.client('s3', region_name='eu-west-1')
    s3.put_object(Bucket=source_bucket_name, Key=filename, Body=b'pdf_content')

    sample_letter_notification.status = NOTIFICATION_PENDING_VIRUS_CHECK
    sample_letter_notification.key_type = key_type
    mock_move_s3 = mocker.patch('app.letters.utils._move_s3_object')

    mock_get_page_count = mocker.patch('app.celery.letters_pdf_tasks._get_page_count', side_effect=PdfReadError)
    mock_sanitise = mocker.patch('app.celery.letters_pdf_tasks._sanitise_precompiled_pdf')

    process_virus_scan_passed(filename)

    mock_sanitise.assert_not_called()
    mock_get_page_count.assert_called_once_with(
        sample_letter_notification, b'pdf_content'
    )
    mock_move_s3.assert_called_once_with(
        source_bucket_name, filename,
        target_bucket_name, filename
    )
    assert sample_letter_notification.status == NOTIFICATION_VALIDATION_FAILED
    assert sample_letter_notification.billable_units == 0


def test_process_letter_task_check_virus_scan_failed(sample_letter_notification, mocker):
    filename = 'NOTIFY.{}'.format(sample_letter_notification.reference)
    sample_letter_notification.status = NOTIFICATION_PENDING_VIRUS_CHECK
    mock_move_failed_pdf = mocker.patch('app.celery.letters_pdf_tasks.move_failed_pdf')

    with pytest.raises(VirusScanError) as e:
        process_virus_scan_failed(filename)

    assert "Virus scan failed:" in str(e)
    mock_move_failed_pdf.assert_called_once_with(filename, ScanErrorType.FAILURE)
    assert sample_letter_notification.status == NOTIFICATION_VIRUS_SCAN_FAILED


def test_process_letter_task_check_virus_scan_error(sample_letter_notification, mocker):
    filename = 'NOTIFY.{}'.format(sample_letter_notification.reference)
    sample_letter_notification.status = NOTIFICATION_PENDING_VIRUS_CHECK
    mock_move_failed_pdf = mocker.patch('app.celery.letters_pdf_tasks.move_failed_pdf')

    with pytest.raises(VirusScanError) as e:
        process_virus_scan_error(filename)

    assert "Virus scan error:" in str(e)
    mock_move_failed_pdf.assert_called_once_with(filename, ScanErrorType.ERROR)
    assert sample_letter_notification.status == NOTIFICATION_TECHNICAL_FAILURE


def test_replay_letters_in_error_for_all_letters_in_error_bucket(notify_api, mocker):
    mockObject = boto3.resource('s3').Object('ERROR', 'ERROR/file_name')
    mocker.patch("app.celery.letters_pdf_tasks.get_file_names_from_error_bucket", return_value=[mockObject])
    mock_move = mocker.patch("app.celery.letters_pdf_tasks.move_error_pdf_to_scan_bucket")
    mock_celery = mocker.patch("app.celery.letters_pdf_tasks.notify_celery.send_task")
    replay_letters_in_error()
    mock_move.assert_called_once_with('file_name')
    mock_celery.assert_called_once_with(name='scan-file', kwargs={'filename': 'file_name'}, queue='antivirus-tasks')


def test_replay_letters_in_error_for_one_file(notify_api, mocker):
    mockObject = boto3.resource('s3').Object('ERROR', 'ERROR/file_name')
    mocker.patch("app.celery.letters_pdf_tasks.get_file_names_from_error_bucket", return_value=[mockObject])
    mock_move = mocker.patch("app.celery.letters_pdf_tasks.move_error_pdf_to_scan_bucket")
    mock_celery = mocker.patch("app.celery.letters_pdf_tasks.notify_celery.send_task")
    replay_letters_in_error("file_name")
    mock_move.assert_called_once_with('file_name')
    mock_celery.assert_called_once_with(name='scan-file', kwargs={'filename': 'file_name'}, queue='antivirus-tasks')


def test_sanitise_precompiled_pdf_returns_data_from_template_preview(rmock, sample_letter_notification):
    sample_letter_notification.status = NOTIFICATION_PENDING_VIRUS_CHECK
    rmock.post('http://localhost:9999/precompiled/sanitise', content=b'new_pdf', status_code=200)
    mock_celery = Mock(**{'retry.side_effect': Retry})

    res = _sanitise_precompiled_pdf(mock_celery, sample_letter_notification, b'old_pdf')

    assert res == b'new_pdf'
    assert rmock.last_request.text == 'old_pdf'


def test_sanitise_precompiled_pdf_returns_none_on_validation_error(rmock, sample_letter_notification):
    sample_letter_notification.status = NOTIFICATION_PENDING_VIRUS_CHECK
    rmock.post('http://localhost:9999/precompiled/sanitise', content=b'new_pdf', status_code=400)
    mock_celery = Mock(**{'retry.side_effect': Retry})

    res = _sanitise_precompiled_pdf(mock_celery, sample_letter_notification, b'old_pdf')

    assert res is None


def test_sanitise_precompiled_pdf_passes_the_service_id_and_notification_id_to_template_preview(
    mocker,
    sample_letter_notification,
):
    tp_mock = mocker.patch('app.celery.letters_pdf_tasks.requests_post')
    sample_letter_notification.status = NOTIFICATION_PENDING_VIRUS_CHECK
    mock_celery = Mock(**{'retry.side_effect': Retry})
    _sanitise_precompiled_pdf(mock_celery, sample_letter_notification, b'old_pdf')

    service_id = str(sample_letter_notification.service_id)
    notification_id = str(sample_letter_notification.id)

    tp_mock.assert_called_once_with(
        'http://localhost:9999/precompiled/sanitise',
        data=b'old_pdf',
        headers={'Authorization': 'Token my-secret-key',
                 'Service-ID': service_id,
                 'Notification-ID': notification_id}
    )


def test_sanitise_precompiled_pdf_retries_on_http_error(rmock, sample_letter_notification):
    sample_letter_notification.status = NOTIFICATION_PENDING_VIRUS_CHECK
    rmock.post('http://localhost:9999/precompiled/sanitise', content=b'new_pdf', status_code=500)
    mock_celery = Mock(**{'retry.side_effect': Retry})

    with pytest.raises(Retry):
        _sanitise_precompiled_pdf(mock_celery, sample_letter_notification, b'old_pdf')


def test_sanitise_precompiled_pdf_sets_notification_to_technical_failure_after_too_many_errors(
    rmock,
    sample_letter_notification
):
    sample_letter_notification.status = NOTIFICATION_PENDING_VIRUS_CHECK
    rmock.post('http://localhost:9999/precompiled/sanitise', content=b'new_pdf', status_code=500)
    mock_celery = Mock(**{'retry.side_effect': MaxRetriesExceededError})

    with pytest.raises(MaxRetriesExceededError):
        _sanitise_precompiled_pdf(mock_celery, sample_letter_notification, b'old_pdf')

    assert sample_letter_notification.status == NOTIFICATION_TECHNICAL_FAILURE
