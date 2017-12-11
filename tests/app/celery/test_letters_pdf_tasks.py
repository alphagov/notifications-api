import pytest
import requests_mock

from botocore.exceptions import ClientError
from celery.exceptions import MaxRetriesExceededError
from requests import RequestException
from sqlalchemy.orm.exc import NoResultFound

from app.celery.letters_pdf_tasks import (
    create_letters_pdf,
    get_letters_pdf,
)

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


def test_create_letters_pdf_calls_upload_letters_pdf(mocker, sample_letter_notification):
    mocker.patch('app.celery.letters_pdf_tasks.get_letters_pdf', return_value=b'\x00\x01')
    mock_s3 = mocker.patch('app.celery.tasks.s3.upload_letters_pdf')

    create_letters_pdf(sample_letter_notification.id)

    mock_s3.assert_called_with(
        reference=sample_letter_notification.reference,
        crown=True,
        filedata=b'\x00\x01'
    )


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
    mocker.patch('app.celery.letters_pdf_tasks.get_letters_pdf')
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
