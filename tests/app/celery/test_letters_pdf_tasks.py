from flask import current_app

from unittest.mock import call

from freezegun import freeze_time
import pytest
import requests_mock
from botocore.exceptions import ClientError
from celery.exceptions import MaxRetriesExceededError
from requests import RequestException
from sqlalchemy.orm.exc import NoResultFound

from app.celery.letters_pdf_tasks import (
    create_letters_pdf,
    get_letters_pdf,
    collate_letter_pdfs_for_day,
    group_letters,
    letter_in_created_state,
    get_letter_pdf_filename,
)
from app.models import Notification, NOTIFICATION_SENDING

from tests.conftest import set_config_values


def test_should_have_decorated_tasks_functions():
    assert create_letters_pdf.__wrapped__.__name__ == 'create_letters_pdf'


@pytest.mark.parametrize('crown_flag,expected_crown_text', [
    (True, 'C'),
    (False, 'N'),
])
@freeze_time("2017-12-04 17:29:00")
def test_get_letter_pdf_filename_returns_correct_filename(
        notify_api, mocker, crown_flag, expected_crown_text):
    filename = get_letter_pdf_filename(reference='foo', crown=crown_flag)

    assert filename == '2017-12-04/NOTIFY.FOO.D.2.C.{}.20171204172900.PDF'.format(expected_crown_text)


@freeze_time("2017-12-04 17:31:00")
def test_get_letter_pdf_filename_returns_tomorrows_filename(notify_api, mocker):
    filename = get_letter_pdf_filename(reference='foo', crown=True)

    assert filename == '2017-12-05/NOTIFY.FOO.D.2.C.C.20171204173100.PDF'


@pytest.mark.parametrize('personalisation', [{'name': 'test'}, None])
def test_get_letters_pdf_calls_notifications_template_preview_service_correctly(
        notify_api, mocker, client, sample_letter_template, personalisation):
    contact_block = 'Mr Foo,\n1 Test Street,\nLondon\nN1'
    dvla_org_id = '002'

    with set_config_values(notify_api, {
        'TEMPLATE_PREVIEW_API_HOST': 'http://localhost/notifications-template-preview',
        'TEMPLATE_PREVIEW_API_KEY': 'test-key'
    }):
        with requests_mock.Mocker() as request_mock:
            mock_post = request_mock.post(
                'http://localhost/notifications-template-preview/print.pdf', content=b'\x00\x01', status_code=200)

            get_letters_pdf(
                sample_letter_template, contact_block=contact_block, org_id=dvla_org_id, values=personalisation)

    assert mock_post.last_request.json() == {
        'values': personalisation,
        'letter_contact_block': contact_block,
        'dvla_org_id': dvla_org_id,
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
    dvla_org_id = '002'

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
                sample_letter_template, contact_block=contact_block, org_id=dvla_org_id, values=None)

    assert billable_units == expected_billable_units


def test_create_letters_pdf_calls_s3upload(mocker, sample_letter_notification):
    mocker.patch('app.celery.letters_pdf_tasks.get_letters_pdf', return_value=(b'\x00\x01', '1'))
    mock_s3 = mocker.patch('app.celery.letters_pdf_tasks.s3upload')

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
    mock_s3 = mocker.patch('app.celery.letters_pdf_tasks.s3upload', side_effect=ClientError({}, 'operation_name'))
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
