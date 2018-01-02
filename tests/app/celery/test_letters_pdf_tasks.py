from unittest.mock import call

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
    group_letters
)
from app.models import Notification

from tests.conftest import set_config_values


def test_should_have_decorated_tasks_functions():
    assert create_letters_pdf.__wrapped__.__name__ == 'create_letters_pdf'


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


def test_create_letters_pdf_calls_upload_letters_pdf(mocker, sample_letter_notification):
    mocker.patch('app.celery.letters_pdf_tasks.get_letters_pdf', return_value=(b'\x00\x01', '1'))
    mock_s3 = mocker.patch('app.celery.tasks.s3.upload_letters_pdf')

    create_letters_pdf(sample_letter_notification.id)

    mock_s3.assert_called_with(
        reference=sample_letter_notification.reference,
        crown=sample_letter_notification.service.crown,
        filedata=b'\x00\x01'
    )


def test_create_letters_pdf_sets_billable_units(mocker, sample_letter_notification):
    mocker.patch('app.celery.letters_pdf_tasks.get_letters_pdf', return_value=(b'\x00\x01', 1))
    mocker.patch('app.celery.tasks.s3.upload_letters_pdf')

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
    mock_s3 = mocker.patch('app.celery.tasks.s3.upload_letters_pdf', side_effect=ClientError({}, 'operation_name'))
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
    assert mock_update_noti.called
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


def test_group_letters_splits_on_file_size(notify_api):
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


def test_group_letters_splits_on_file_count(notify_api):
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


def test_group_letters_ignores_non_pdfs(notify_api):
    letters = [{'Key': 'A.zip'}]
    assert list(group_letters(letters)) == []


def test_group_letters_with_no_letters(notify_api):
    assert list(group_letters([])) == []
