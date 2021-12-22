import uuid
from collections import namedtuple
from datetime import datetime, timedelta
from unittest.mock import call

import boto3
import pytest
from botocore.exceptions import ClientError
from celery.exceptions import MaxRetriesExceededError
from flask import current_app
from freezegun import freeze_time
from moto import mock_s3
from sqlalchemy.orm.exc import NoResultFound

from app import encryption
from app.celery.letters_pdf_tasks import (
    _move_invalid_letter_and_update_status,
    collate_letter_pdfs_to_be_sent,
    get_key_and_size_of_letters_to_be_sent_to_print,
    get_pdf_for_templated_letter,
    group_letters,
    process_sanitised_letter,
    process_virus_scan_error,
    process_virus_scan_failed,
    replay_letters_in_error,
    resanitise_pdf,
    sanitise_letter,
    send_letters_volume_email_to_dvla,
    update_billable_units_for_letter,
)
from app.config import QueueNames, TaskNames
from app.dao.notifications_dao import get_notifications
from app.errors import VirusScanError
from app.exceptions import NotificationTechnicalFailureException
from app.letters.utils import ScanErrorType
from app.models import (
    INTERNATIONAL_LETTERS,
    KEY_TYPE_NORMAL,
    KEY_TYPE_TEST,
    LETTER_TYPE,
    NOTIFICATION_CREATED,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_PENDING_VIRUS_CHECK,
    NOTIFICATION_TECHNICAL_FAILURE,
    NOTIFICATION_VALIDATION_FAILED,
    NOTIFICATION_VIRUS_SCAN_FAILED,
    Notification,
)
from tests.app.db import (
    create_letter_branding,
    create_notification,
    create_organisation,
    create_service,
    create_template,
)
from tests.conftest import set_config_values


def test_should_have_decorated_tasks_functions():
    assert get_pdf_for_templated_letter.__wrapped__.__name__ == 'get_pdf_for_templated_letter'
    assert collate_letter_pdfs_to_be_sent.__wrapped__.__name__ == 'collate_letter_pdfs_to_be_sent'
    assert process_virus_scan_failed.__wrapped__.__name__ == 'process_virus_scan_failed'
    assert process_virus_scan_error.__wrapped__.__name__ == 'process_virus_scan_error'
    assert sanitise_letter.__wrapped__.__name__ == 'sanitise_letter'
    assert process_sanitised_letter.__wrapped__.__name__ == 'process_sanitised_letter'


@pytest.mark.parametrize('branding_name,logo_filename', [(None, None), ['Test Brand', 'test-brand']])
def test_get_pdf_for_templated_letter_happy_path(mocker, sample_letter_notification, branding_name, logo_filename):
    if branding_name:
        letter_branding = create_letter_branding(name=branding_name, filename=logo_filename)
        sample_letter_notification.service.letter_branding = letter_branding
    mock_celery = mocker.patch('app.celery.letters_pdf_tasks.notify_celery.send_task')
    mock_generate_letter_pdf_filename = mocker.patch(
        'app.celery.letters_pdf_tasks.generate_letter_pdf_filename',
        return_value='LETTER.PDF'
    )
    get_pdf_for_templated_letter(sample_letter_notification.id)

    letter_data = {
        'letter_contact_block': sample_letter_notification.reply_to_text,
        'template': {
            "subject": sample_letter_notification.template.subject,
            "content": sample_letter_notification.template.content,
            "template_type": sample_letter_notification.template.template_type
        },
        'values': sample_letter_notification.personalisation,
        'logo_filename': logo_filename,
        'letter_filename': 'LETTER.PDF',
        "notification_id": str(sample_letter_notification.id),
        'key_type': sample_letter_notification.key_type
    }

    encrypted_data = encryption.encrypt(letter_data)

    mock_celery.assert_called_once_with(
        name=TaskNames.CREATE_PDF_FOR_TEMPLATED_LETTER,
        args=(encrypted_data,),
        queue=QueueNames.SANITISE_LETTERS
    )

    mock_generate_letter_pdf_filename.assert_called_once_with(
        reference=sample_letter_notification.reference,
        created_at=sample_letter_notification.created_at,
        ignore_folder=False,
        postage='second'
    )


def test_get_pdf_for_templated_letter_non_existent_notification(notify_db_session, mocker, fake_uuid):
    with pytest.raises(expected_exception=NoResultFound):
        get_pdf_for_templated_letter(fake_uuid)


def test_get_pdf_for_templated_letter_retries_upon_error(mocker, sample_letter_notification):
    mock_celery = mocker.patch('app.celery.letters_pdf_tasks.notify_celery.send_task', side_effect=Exception())
    mocker.patch('app.celery.letters_pdf_tasks.generate_letter_pdf_filename', return_value='LETTER.PDF')
    mock_retry = mocker.patch('app.celery.letters_pdf_tasks.get_pdf_for_templated_letter.retry')
    mock_logger = mocker.patch('app.celery.tasks.current_app.logger.exception')

    get_pdf_for_templated_letter(sample_letter_notification.id)

    assert mock_celery.called
    assert mock_retry.called
    mock_logger.assert_called_once_with(
        f"RETRY: calling create-letter-pdf task for notification {sample_letter_notification.id} failed"
    )


def test_get_pdf_for_templated_letter_sets_technical_failure_max_retries(mocker, sample_letter_notification):
    mock_celery = mocker.patch('app.celery.letters_pdf_tasks.notify_celery.send_task', side_effect=Exception())
    mocker.patch('app.celery.letters_pdf_tasks.generate_letter_pdf_filename', return_value='LETTER.PDF')
    mock_retry = mocker.patch(
        'app.celery.letters_pdf_tasks.get_pdf_for_templated_letter.retry', side_effect=MaxRetriesExceededError)
    mock_update_noti = mocker.patch('app.celery.letters_pdf_tasks.update_notification_status_by_id')

    with pytest.raises(NotificationTechnicalFailureException) as e:
        get_pdf_for_templated_letter(sample_letter_notification.id)

    assert e.value.args[0] == f"RETRY FAILED: Max retries reached. " \
        f"The task create-letter-pdf failed for notification id {sample_letter_notification.id}. " \
        f"Notification has been updated to technical-failure"
    assert mock_celery.called
    assert mock_retry.called
    mock_update_noti.assert_called_once_with(sample_letter_notification.id, 'technical-failure')


@pytest.mark.parametrize('number_of_pages, expected_billable_units', [(2, 1), (3, 2), (10, 5)])
def test_update_billable_units_for_letter(mocker, sample_letter_notification, number_of_pages, expected_billable_units):
    sample_letter_notification.billable_units = 0
    mock_logger = mocker.patch('app.celery.tasks.current_app.logger.info')

    update_billable_units_for_letter(sample_letter_notification.id, number_of_pages)

    notification = Notification.query.filter(Notification.reference == sample_letter_notification.reference).one()
    assert notification.billable_units == expected_billable_units
    mock_logger.assert_called_once_with(
        f"Letter notification id: {sample_letter_notification.id} reference {sample_letter_notification.reference}:"
        f" billable units set to {expected_billable_units}"
    )


def test_update_billable_units_for_letter_doesnt_update_if_sent_with_test_key(mocker, sample_letter_notification):
    sample_letter_notification.billable_units = 0
    sample_letter_notification.key_type = KEY_TYPE_TEST
    mock_logger = mocker.patch('app.celery.tasks.current_app.logger.info')

    update_billable_units_for_letter(sample_letter_notification.id, 2)

    notification = Notification.query.filter(Notification.reference == sample_letter_notification.reference).one()
    assert notification.billable_units == 0
    mock_logger.assert_not_called()


def test_update_billable_units_for_letter_with_over_10_pages(
        mocker, sample_letter_notification
):
    sample_letter_notification.billable_units = 0
    mock_logger = mocker.patch('app.celery.tasks.current_app.logger.info')
    mock_move = mocker.patch('app.celery.letters_pdf_tasks.move_invalid_templated_letter_to_invalid_bucket')

    update_billable_units_for_letter(sample_letter_notification.id, 11)

    notification = Notification.query.filter(Notification.reference == sample_letter_notification.reference).one()
    assert notification.billable_units == 0
    assert notification.status == NOTIFICATION_VALIDATION_FAILED
    mock_logger.assert_called_once_with(
        f"Templated letter notification id: {notification.id} reference {notification.reference}: "
        f"is too long page_count: {11} status set to validation-failed"
    )
    mock_move.assert_called_once_with(
        11,
        notification.key_type,
        notification.reference,
        notification.created_at,
        notification.postage
    )


@mock_s3
@freeze_time('2020-02-17 18:00:00')
def test_get_key_and_size_of_letters_to_be_sent_to_print(
    notify_api,
    mocker,
    sample_letter_template,
    sample_organisation,
):
    pdf_bucket = current_app.config['LETTERS_PDF_BUCKET_NAME']
    s3 = boto3.client('s3', region_name='eu-west-1')
    s3.create_bucket(Bucket=pdf_bucket, CreateBucketConfiguration={'LocationConstraint': 'eu-west-1'})
    s3.put_object(Bucket=pdf_bucket, Key='2020-02-17/NOTIFY.REF0.D.2.C.20200217160000.PDF', Body=b'1'),
    s3.put_object(Bucket=pdf_bucket, Key='2020-02-17/NOTIFY.REF1.D.2.C.20200217150000.PDF', Body=b'22'),
    s3.put_object(Bucket=pdf_bucket, Key='2020-02-16/NOTIFY.REF2.D.2.C.20200215180000.PDF', Body=b'333'),

    sample_letter_template.service.organisation = sample_organisation

    # second class
    create_notification(
        template=sample_letter_template,
        status='created',
        reference='ref0',
        created_at=(datetime.now() - timedelta(hours=2))
    )
    create_notification(
        template=sample_letter_template,
        status='created',
        reference='ref1',
        created_at=(datetime.now() - timedelta(hours=3))
    )
    create_notification(
        template=sample_letter_template,
        status='created',
        reference='ref2',
        created_at=(datetime.now() - timedelta(days=2))
    )

    # notifications we don't expect to get sent to print as they are in the wrong status
    for status in ['delivered', 'validation-failed', 'cancelled', 'sending']:
        create_notification(
            template=sample_letter_template,
            status=status,
            reference='ref3',
            created_at=(datetime.now() - timedelta(days=2))
        )

    # notification we don't expect to get sent as instead will make into this evenings print run
    create_notification(
        template=sample_letter_template,
        status='created',
        reference='ref4',
        created_at=(datetime.now() - timedelta(minutes=1))
    )

    # test notification we don't expect to get sent
    create_notification(
        template=sample_letter_template,
        status='created',
        reference='ref4',
        created_at=(datetime.now() - timedelta(days=1)),
        key_type=KEY_TYPE_TEST
    )

    results = list(
        get_key_and_size_of_letters_to_be_sent_to_print(datetime.now() - timedelta(minutes=30), postage='second')
    )

    assert len(results) == 3

    assert results == [
        {

            'Key': '2020-02-16/NOTIFY.REF2.D.2.C.20200215180000.PDF',
            'Size': 3,
            'ServiceId': str(sample_letter_template.service_id),
            'OrganisationId': str(sample_organisation.id)
        },
        {
            'Key': '2020-02-17/NOTIFY.REF1.D.2.C.20200217150000.PDF',
            'Size': 2,
            'ServiceId': str(sample_letter_template.service_id),
            'OrganisationId': str(sample_organisation.id)
        },
        {
            'Key': '2020-02-17/NOTIFY.REF0.D.2.C.20200217160000.PDF',
            'Size': 1,
            'ServiceId': str(sample_letter_template.service_id),
            'OrganisationId': str(sample_organisation.id)
        },
    ]


@mock_s3
@freeze_time('2020-02-17 18:00:00')
def test_get_key_and_size_of_letters_to_be_sent_to_print_handles_file_not_found(
    notify_api, mocker, sample_letter_template, sample_organisation
):
    pdf_bucket = current_app.config['LETTERS_PDF_BUCKET_NAME']
    s3 = boto3.client('s3', region_name='eu-west-1')
    s3.create_bucket(Bucket=pdf_bucket, CreateBucketConfiguration={'LocationConstraint': 'eu-west-1'})
    s3.put_object(Bucket=pdf_bucket, Key='2020-02-17/NOTIFY.REF1.D.2.C.20200217150000.PDF', Body=b'12'),
    # no object for ref1

    sample_letter_template.service.organisation = sample_organisation

    create_notification(
        template=sample_letter_template,
        status='created',
        reference='ref0',
        created_at=(datetime.now() - timedelta(hours=2))
    )

    create_notification(
        template=sample_letter_template,
        status='created',
        reference='ref1',
        created_at=(datetime.now() - timedelta(hours=3))
    )

    results = list(
        get_key_and_size_of_letters_to_be_sent_to_print(datetime.now() - timedelta(minutes=30), postage='second')
    )

    assert results == [{
        'Key': '2020-02-17/NOTIFY.REF1.D.2.C.20200217150000.PDF',
        'Size': 2,
        'ServiceId': str(sample_letter_template.service_id),
        'OrganisationId': str(sample_organisation.id)}
    ]


@mock_s3
@pytest.mark.parametrize('time_to_run_task', [
    "2020-02-17 18:00:00",  # after 5:30pm
    "2020-02-18 02:00:00",  # the next day after midnight, before 5:30pm we expect the same results
])
def test_collate_letter_pdfs_to_be_sent(
    notify_api, mocker, time_to_run_task, sample_organisation
):
    with freeze_time("2020-02-17 18:00:00"):
        service_1 = create_service(service_name="service 1", service_id='f2fe37b0-1301-11eb-aba9-4c3275916899')
        service_1.organisation = sample_organisation
        letter_template_1 = create_template(service_1, template_type=LETTER_TYPE)
        # second class
        create_notification(
            template=letter_template_1,
            status='created',
            reference='ref0',
            created_at=(datetime.now() - timedelta(hours=2))
        )
        create_notification(
            template=letter_template_1,
            status='created',
            reference='ref1',
            created_at=(datetime.now() - timedelta(hours=3))
        )
        create_notification(
            template=letter_template_1,
            status='created',
            reference='ref2',
            created_at=(datetime.now() - timedelta(days=2))
        )

        # first class
        create_notification(
            template=letter_template_1,
            status='created',
            reference='first_class',
            created_at=(datetime.now() - timedelta(hours=4)),
            postage="first"
        )

        # international
        create_notification(
            template=letter_template_1,
            status='created',
            reference='international',
            created_at=(datetime.now() - timedelta(days=3)),
            postage="europe"
        )
        create_notification(
            template=letter_template_1,
            status='created',
            reference='international',
            created_at=(datetime.now() - timedelta(days=4)),
            postage="rest-of-world"
        )

        # different service second class, belonging to a different organisation
        org_2_id = uuid.uuid4()
        organisation_two = create_organisation('Org 2', organisation_id=org_2_id)
        service_2 = create_service(service_name="service 2",
                                   service_id='3a5cea08-29fd-4bb9-b582-8dedd928b149',
                                   organisation=organisation_two)
        letter_template_2 = create_template(service_2, template_type=LETTER_TYPE)
        create_notification(
            template=letter_template_2,
            status='created',
            reference='another_service',
            created_at=(datetime.now() - timedelta(hours=2))
        )

    bucket_name = current_app.config['LETTERS_PDF_BUCKET_NAME']
    s3 = boto3.client('s3', region_name='eu-west-1')
    s3.create_bucket(
        Bucket=bucket_name,
        CreateBucketConfiguration={'LocationConstraint': 'eu-west-1'}
    )

    filenames = [
        '2020-02-17/NOTIFY.FIRST_CLASS.D.1.C.20200217140000.PDF',
        '2020-02-16/NOTIFY.REF2.D.2.C.20200215180000.PDF',
        '2020-02-17/NOTIFY.REF1.D.2.C.20200217150000.PDF',
        '2020-02-17/NOTIFY.REF0.D.2.C.20200217160000.PDF',
        '2020-02-15/NOTIFY.INTERNATIONAL.D.E.C.20200214180000.PDF',
        '2020-02-14/NOTIFY.INTERNATIONAL.D.N.C.20200213180000.PDF',
        '2020-02-17/NOTIFY.ANOTHER_SERVICE.D.2.C.20200217160000.PDF'
    ]

    for filename in filenames:
        s3.put_object(Bucket=bucket_name, Key=filename, Body=b'f')

    mock_celery = mocker.patch('app.celery.letters_pdf_tasks.notify_celery.send_task')
    mock_send_email_to_dvla = mocker.patch(
        'app.celery.letters_pdf_tasks.send_letters_volume_email_to_dvla'
    )

    with set_config_values(notify_api, {'MAX_LETTER_PDF_COUNT_PER_ZIP': 2}):
        with freeze_time(time_to_run_task):
            collate_letter_pdfs_to_be_sent()

    mock_send_email_to_dvla.assert_called_once_with([
        (1, 1, 'europe'), (1, 1, 'first'), (1, 1, 'rest-of-world'), (4, 4, 'second')
    ], datetime(2020, 2, 17).date())

    assert len(mock_celery.call_args_list) == 6
    assert mock_celery.call_args_list[0] == call(
        name='zip-and-send-letter-pdfs',
        kwargs={
            'filenames_to_zip': [
                '2020-02-17/NOTIFY.FIRST_CLASS.D.1.C.20200217140000.PDF'
            ],
            'upload_filename':
            f'NOTIFY.2020-02-17.1.001.sO6RKzPyNrkxrR8OLonl.{letter_template_1.service_id}.{sample_organisation.id}.ZIP'
        },
        queue='process-ftp-tasks',
        compression='zlib'
    )
    assert mock_celery.call_args_list[1] == call(
        name='zip-and-send-letter-pdfs',
        kwargs={
            'filenames_to_zip': ['2020-02-17/NOTIFY.ANOTHER_SERVICE.D.2.C.20200217160000.PDF'],
            'upload_filename':
            f'NOTIFY.2020-02-17.2.001.bGS-FKKV0QHcOUZgacEu.{service_2.id}.{org_2_id}.ZIP'
        },
        queue='process-ftp-tasks',
        compression='zlib'
    )
    assert mock_celery.call_args_list[2] == call(
        name='zip-and-send-letter-pdfs',
        kwargs={
            'filenames_to_zip': [
                '2020-02-16/NOTIFY.REF2.D.2.C.20200215180000.PDF',
                '2020-02-17/NOTIFY.REF1.D.2.C.20200217150000.PDF'
            ],
            'upload_filename':
            f'NOTIFY.2020-02-17.2.002.AmmswUYqPToXwlSZiFyK.{letter_template_1.service_id}.{sample_organisation.id}.ZIP'
        },
        queue='process-ftp-tasks',
        compression='zlib'
    )
    assert mock_celery.call_args_list[3] == call(
        name='zip-and-send-letter-pdfs',
        kwargs={
            'filenames_to_zip': [
                '2020-02-17/NOTIFY.REF0.D.2.C.20200217160000.PDF'
            ],
            'upload_filename':
            f'NOTIFY.2020-02-17.2.003.36PwhyI9lFKjzbPiWxwv.{letter_template_1.service_id}.{sample_organisation.id}.ZIP'
        },
        queue='process-ftp-tasks',
        compression='zlib'
    )
    assert mock_celery.call_args_list[4] == call(
        name='zip-and-send-letter-pdfs',
        kwargs={
            'filenames_to_zip': [
                '2020-02-15/NOTIFY.INTERNATIONAL.D.E.C.20200214180000.PDF'
            ],
            'upload_filename':
            f'NOTIFY.2020-02-17.E.001.lDBwqhnG__URJeGz3tH1.{letter_template_1.service_id}.{sample_organisation.id}.ZIP'
        },
        queue='process-ftp-tasks',
        compression='zlib'
    )
    assert mock_celery.call_args_list[5] == call(
        name='zip-and-send-letter-pdfs',
        kwargs={
            'filenames_to_zip': [
                '2020-02-14/NOTIFY.INTERNATIONAL.D.N.C.20200213180000.PDF',
            ],
            'upload_filename':
            f'NOTIFY.2020-02-17.N.001.ZE7k_jm7Bg5sYwLswkr4.{letter_template_1.service_id}.{sample_organisation.id}.ZIP'
        },
        queue='process-ftp-tasks',
        compression='zlib'
    )


def test_send_letters_volume_email_to_dvla(notify_api, notify_db_session, mocker, letter_volumes_email_template):
    MockVolume = namedtuple('LettersVolume', ['postage', 'letters_count', 'sheets_count'])
    letters_volumes = [
        MockVolume('first', 5, 7),
        MockVolume('second', 4, 12),
        MockVolume('europe', 1, 3),
        MockVolume('rest-of-world', 1, 2),
    ]
    send_mock = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')

    send_letters_volume_email_to_dvla(letters_volumes, datetime(2020, 2, 17).date())

    emails_to_dvla = get_notifications().all()
    assert len(emails_to_dvla) == 2
    send_mock.called = 2
    send_mock.assert_any_call([str(emails_to_dvla[0].id)], queue=QueueNames.NOTIFY)
    send_mock.assert_any_call([str(emails_to_dvla[1].id)], queue=QueueNames.NOTIFY)
    for email in emails_to_dvla:
        assert str(email.template_id) == current_app.config['LETTERS_VOLUME_EMAIL_TEMPLATE_ID']
        assert email.to in current_app.config['DVLA_EMAIL_ADDRESSES']
        assert email.personalisation == {
            'total_volume': 11,
            'first_class_volume': 5,
            'second_class_volume': 4,
            'international_volume': 2,
            'total_sheets': 24,
            'first_class_sheets': 7,
            "second_class_sheets": 12,
            'international_sheets': 5,
            'date': '17 February 2020'
        }


def test_group_letters_splits_on_file_size(notify_api):
    letters = [
        # ends under max but next one is too big
        {'Key': 'A.pdf', 'Size': 1, 'ServiceId': '123'}, {'Key': 'B.pdf', 'Size': 2, 'ServiceId': '123'},
        # ends on exactly max
        {'Key': 'C.pdf', 'Size': 3, 'ServiceId': '123'},
        {'Key': 'D.pdf', 'Size': 1, 'ServiceId': '123'},
        {'Key': 'E.pdf', 'Size': 1, 'ServiceId': '123'},
        # exactly max goes in next file
        {'Key': 'F.pdf', 'Size': 5, 'ServiceId': '123'},
        # if it's bigger than the max, still gets included
        {'Key': 'G.pdf', 'Size': 6, 'ServiceId': '123'},
        # whatever's left goes in last list
        {'Key': 'H.pdf', 'Size': 1, 'ServiceId': '123'}, {'Key': 'I.pdf', 'Size': 1, 'ServiceId': '123'},
    ]

    with set_config_values(notify_api, {'MAX_LETTER_PDF_ZIP_FILESIZE': 5}):
        x = group_letters(letters)

        assert next(x) == [
            {'Key': 'A.pdf', 'Size': 1, 'ServiceId': '123'},
            {'Key': 'B.pdf', 'Size': 2, 'ServiceId': '123'}
        ]
        assert next(x) == [
            {'Key': 'C.pdf', 'Size': 3, 'ServiceId': '123'},
            {'Key': 'D.pdf', 'Size': 1, 'ServiceId': '123'},
            {'Key': 'E.pdf', 'Size': 1, 'ServiceId': '123'}
        ]
        assert next(x) == [{'Key': 'F.pdf', 'Size': 5, 'ServiceId': '123'}]
        assert next(x) == [{'Key': 'G.pdf', 'Size': 6, 'ServiceId': '123'}]
        assert next(x) == [
            {'Key': 'H.pdf', 'Size': 1, 'ServiceId': '123'},
            {'Key': 'I.pdf', 'Size': 1, 'ServiceId': '123'}
        ]
        # make sure iterator is exhausted
        assert next(x, None) is None


def test_group_letters_splits_on_file_count(notify_api):
    letters = [
        {'Key': 'A.pdf', 'Size': 1, 'ServiceId': '123'},
        {'Key': 'B.pdf', 'Size': 2, 'ServiceId': '123'},
        {'Key': 'C.pdf', 'Size': 3, 'ServiceId': '123'},
        {'Key': 'D.pdf', 'Size': 1, 'ServiceId': '123'},
        {'Key': 'E.pdf', 'Size': 1, 'ServiceId': '123'},
        {'Key': 'F.pdf', 'Size': 5, 'ServiceId': '123'},
        {'Key': 'G.pdf', 'Size': 6, 'ServiceId': '123'},
        {'Key': 'H.pdf', 'Size': 1, 'ServiceId': '123'},
        {'Key': 'I.pdf', 'Size': 1, 'ServiceId': '123'},
    ]

    with set_config_values(notify_api, {'MAX_LETTER_PDF_COUNT_PER_ZIP': 3}):
        x = group_letters(letters)

        assert next(x) == [
            {'Key': 'A.pdf', 'Size': 1, 'ServiceId': '123'},
            {'Key': 'B.pdf', 'Size': 2, 'ServiceId': '123'},
            {'Key': 'C.pdf', 'Size': 3, 'ServiceId': '123'}
        ]
        assert next(x) == [
            {'Key': 'D.pdf', 'Size': 1, 'ServiceId': '123'},
            {'Key': 'E.pdf', 'Size': 1, 'ServiceId': '123'},
            {'Key': 'F.pdf', 'Size': 5, 'ServiceId': '123'}
        ]
        assert next(x) == [
            {'Key': 'G.pdf', 'Size': 6, 'ServiceId': '123'},
            {'Key': 'H.pdf', 'Size': 1, 'ServiceId': '123'},
            {'Key': 'I.pdf', 'Size': 1, 'ServiceId': '123'}
        ]
        # make sure iterator is exhausted
        assert next(x, None) is None


def test_group_letters_splits_on_file_size_and_file_count(notify_api):
    letters = [
        # ends under max file size but next file is too big
        {'Key': 'A.pdf', 'Size': 1, 'ServiceId': '123'},
        {'Key': 'B.pdf', 'Size': 2, 'ServiceId': '123'},
        # ends on exactly max number of files and file size
        {'Key': 'C.pdf', 'Size': 3, 'ServiceId': '123'},
        {'Key': 'D.pdf', 'Size': 1, 'ServiceId': '123'},
        {'Key': 'E.pdf', 'Size': 1, 'ServiceId': '123'},
        # exactly max file size goes in next file
        {'Key': 'F.pdf', 'Size': 5, 'ServiceId': '123'},
        # file size is within max but number of files reaches limit
        {'Key': 'G.pdf', 'Size': 1, 'ServiceId': '123'},
        {'Key': 'H.pdf', 'Size': 1, 'ServiceId': '123'},
        {'Key': 'I.pdf', 'Size': 1, 'ServiceId': '123'},
        # whatever's left goes in last list
        {'Key': 'J.pdf', 'Size': 1, 'ServiceId': '123'},
    ]

    with set_config_values(notify_api, {
        'MAX_LETTER_PDF_ZIP_FILESIZE': 5,
        'MAX_LETTER_PDF_COUNT_PER_ZIP': 3
    }):
        x = group_letters(letters)

        assert next(x) == [
            {'Key': 'A.pdf', 'Size': 1, 'ServiceId': '123'},
            {'Key': 'B.pdf', 'Size': 2, 'ServiceId': '123'}
        ]
        assert next(x) == [
            {'Key': 'C.pdf', 'Size': 3, 'ServiceId': '123'},
            {'Key': 'D.pdf', 'Size': 1, 'ServiceId': '123'},
            {'Key': 'E.pdf', 'Size': 1, 'ServiceId': '123'}
        ]
        assert next(x) == [{'Key': 'F.pdf', 'Size': 5, 'ServiceId': '123'}]
        assert next(x) == [
            {'Key': 'G.pdf', 'Size': 1, 'ServiceId': '123'},
            {'Key': 'H.pdf', 'Size': 1, 'ServiceId': '123'},
            {'Key': 'I.pdf', 'Size': 1, 'ServiceId': '123'}
        ]
        assert next(x) == [{'Key': 'J.pdf', 'Size': 1, 'ServiceId': '123'}]
        # make sure iterator is exhausted
        assert next(x, None) is None


@pytest.mark.parametrize('key', ["A.ZIP", "B.zip"])
def test_group_letters_ignores_non_pdfs(key):
    letters = [{'Key': key, 'Size': 1}]
    assert list(group_letters(letters)) == []


@pytest.mark.parametrize('key', ["A.PDF", "B.pdf", "C.PdF"])
def test_group_letters_includes_pdf_files(key):
    letters = [{'Key': key, 'Size': 1, 'ServiceId': '123'}]
    assert list(group_letters(letters)) == [[{'Key': key, 'Size': 1, 'ServiceId': '123'}]]


def test_group_letters_with_no_letters():
    assert list(group_letters([])) == []


def test_move_invalid_letter_and_update_status_logs_error_and_sets_tech_failure_state_if_s3_error(
    mocker,
    sample_letter_notification,
):
    error_response = {
        'Error': {
            'Code': 'InvalidParameterValue',
            'Message': 'some error message from amazon',
            'Type': 'Sender'
        }
    }
    mocker.patch('app.celery.letters_pdf_tasks.move_scan_to_invalid_pdf_bucket',
                 side_effect=ClientError(error_response, 'operation_name'))
    mock_logger = mocker.patch('app.celery.tasks.current_app.logger.exception')

    with pytest.raises(NotificationTechnicalFailureException):
        _move_invalid_letter_and_update_status(
            notification=sample_letter_notification,
            filename='filename',
            scan_pdf_object=mocker.Mock()
        )

    assert sample_letter_notification.status == NOTIFICATION_TECHNICAL_FAILURE
    mock_logger.assert_called_once_with(
        'Error when moving letter with id {} to invalid PDF bucket'.format(sample_letter_notification.id)
    )


@pytest.mark.parametrize('permissions, expected_international_letters_allowed', (
    ([LETTER_TYPE], False),
    ([LETTER_TYPE, INTERNATIONAL_LETTERS], True),
))
def test_sanitise_letter_calls_template_preview_sanitise_task(
    mocker,
    sample_letter_notification,
    permissions,
    expected_international_letters_allowed,
):
    mock_celery = mocker.patch('app.celery.letters_pdf_tasks.notify_celery.send_task')
    filename = 'NOTIFY.{}'.format(sample_letter_notification.reference)
    sample_letter_notification.service = create_service(
        service_permissions=permissions
    )
    sample_letter_notification.status = NOTIFICATION_PENDING_VIRUS_CHECK

    sanitise_letter(filename)

    mock_celery.assert_called_once_with(
        name=TaskNames.SANITISE_LETTER,
        kwargs={
            'notification_id': str(sample_letter_notification.id),
            'filename': filename,
            'allow_international_letters': expected_international_letters_allowed,
        },
        queue=QueueNames.SANITISE_LETTERS,
    )


def test_sanitise_letter_does_not_call_template_preview_sanitise_task_if_notification_in_wrong_state(
    mocker,
    sample_letter_notification,
):
    mock_celery = mocker.patch('app.celery.letters_pdf_tasks.notify_celery.send_task')
    filename = 'NOTIFY.{}'.format(sample_letter_notification.reference)

    sanitise_letter(filename)

    assert not mock_celery.called


def test_sanitise_letter_does_not_call_template_preview_sanitise_task_if_there_is_an_exception(
    mocker,
    sample_letter_notification,
):
    mocker.patch('app.celery.letters_pdf_tasks.notify_celery.send_task', side_effect=Exception())
    mock_celery_retry = mocker.patch('app.celery.letters_pdf_tasks.sanitise_letter.retry')

    filename = 'NOTIFY.{}'.format(sample_letter_notification.reference)
    sample_letter_notification.status = NOTIFICATION_PENDING_VIRUS_CHECK

    sanitise_letter(filename)

    mock_celery_retry.assert_called_once_with(queue='retry-tasks')


def test_sanitise_letter_puts_letter_into_technical_failure_if_max_retries_exceeded(sample_letter_notification, mocker):
    mocker.patch('app.celery.letters_pdf_tasks.notify_celery.send_task', side_effect=Exception())
    mocker.patch('app.celery.letters_pdf_tasks.sanitise_letter.retry', side_effect=MaxRetriesExceededError())

    filename = 'NOTIFY.{}'.format(sample_letter_notification.reference)
    sample_letter_notification.status = NOTIFICATION_PENDING_VIRUS_CHECK

    with pytest.raises(NotificationTechnicalFailureException):
        sanitise_letter(filename)

    assert sample_letter_notification.status == NOTIFICATION_TECHNICAL_FAILURE


@mock_s3
@pytest.mark.parametrize('key_type, destination_bucket, expected_status, postage, destination_filename', [
    (
        KEY_TYPE_NORMAL,
        'LETTERS_PDF_BUCKET_NAME',
        NOTIFICATION_CREATED,
        'first',
        '2018-07-01/NOTIFY.FOO.D.1.C.20180701120000.PDF'
    ),
    (
        KEY_TYPE_NORMAL,
        'LETTERS_PDF_BUCKET_NAME',
        NOTIFICATION_CREATED,
        'second',
        '2018-07-01/NOTIFY.FOO.D.2.C.20180701120000.PDF'
    ),
    (
        KEY_TYPE_NORMAL,
        'LETTERS_PDF_BUCKET_NAME',
        NOTIFICATION_CREATED,
        'europe',
        '2018-07-01/NOTIFY.FOO.D.E.C.20180701120000.PDF'
    ),
    (
        KEY_TYPE_NORMAL,
        'LETTERS_PDF_BUCKET_NAME',
        NOTIFICATION_CREATED,
        'rest-of-world',
        '2018-07-01/NOTIFY.FOO.D.N.C.20180701120000.PDF'
    ),
    (
        KEY_TYPE_TEST,
        'TEST_LETTERS_BUCKET_NAME',
        NOTIFICATION_DELIVERED,
        'second',
        'NOTIFY.FOO.D.2.C.20180701120000.PDF',
    ),
    (
        KEY_TYPE_TEST,
        'TEST_LETTERS_BUCKET_NAME',
        NOTIFICATION_DELIVERED,
        'first',
        'NOTIFY.FOO.D.1.C.20180701120000.PDF',
    ),
])
def test_process_sanitised_letter_with_valid_letter(
    sample_letter_notification,
    key_type,
    destination_bucket,
    expected_status,
    postage,
    destination_filename,
):
    # We save the letter as if it's 2nd class initially, and the task changes the filename to have the correct postage
    filename = 'NOTIFY.FOO.D.2.C.20180701120000.PDF'

    scan_bucket_name = current_app.config['LETTERS_SCAN_BUCKET_NAME']
    template_preview_bucket_name = current_app.config['LETTER_SANITISE_BUCKET_NAME']
    destination_bucket_name = current_app.config[destination_bucket]
    conn = boto3.resource('s3', region_name='eu-west-1')

    scan_bucket = conn.create_bucket(
        Bucket=scan_bucket_name,
        CreateBucketConfiguration={'LocationConstraint': 'eu-west-1'}
    )
    template_preview_bucket = conn.create_bucket(
        Bucket=template_preview_bucket_name,
        CreateBucketConfiguration={'LocationConstraint': 'eu-west-1'}
    )
    destination_bucket = conn.create_bucket(
        Bucket=destination_bucket_name,
        CreateBucketConfiguration={'LocationConstraint': 'eu-west-1'}
    )

    s3 = boto3.client('s3', region_name='eu-west-1')
    s3.put_object(Bucket=scan_bucket_name, Key=filename, Body=b'original_pdf_content')
    s3.put_object(Bucket=template_preview_bucket_name, Key=filename, Body=b'sanitised_pdf_content')

    sample_letter_notification.status = NOTIFICATION_PENDING_VIRUS_CHECK
    sample_letter_notification.key_type = key_type
    sample_letter_notification.billable_units = 1
    sample_letter_notification.created_at = datetime(2018, 7, 1, 12)
    sample_letter_notification.postage = postage

    encrypted_data = encryption.encrypt({
        'page_count': 2,
        'message': None,
        'invalid_pages': None,
        'validation_status': 'passed',
        'filename': filename,
        'notification_id': str(sample_letter_notification.id),
        'address': 'A. User\nThe house on the corner'
    })
    process_sanitised_letter(encrypted_data)

    assert sample_letter_notification.status == expected_status
    assert sample_letter_notification.billable_units == 1
    assert sample_letter_notification.to == 'A. User\nThe house on the corner'
    assert sample_letter_notification.normalised_to == 'a.userthehouseonthecorner'

    assert not [x for x in scan_bucket.objects.all()]
    assert not [x for x in template_preview_bucket.objects.all()]
    assert len([x for x in destination_bucket.objects.all()]) == 1

    file_contents = conn.Object(destination_bucket_name, destination_filename).get()['Body'].read().decode('utf-8')
    assert file_contents == 'sanitised_pdf_content'


@mock_s3
@pytest.mark.parametrize('address, expected_postage, expected_international',
                         [('Lady Lou, 123 Main Street, SW1 1AA', 'second', False),
                          ('Lady Lou, 123 Main Street, France', 'europe', True),
                          ('Lady Lou, 123 Main Street, New Zealand', 'rest-of-world', True),
                          ])
def test_process_sanitised_letter_sets_postage_international(
    sample_letter_notification,
    expected_postage,
    expected_international,
    address
):
    filename = 'NOTIFY.{}'.format(sample_letter_notification.reference)

    scan_bucket_name = current_app.config['LETTERS_SCAN_BUCKET_NAME']
    template_preview_bucket_name = current_app.config['LETTER_SANITISE_BUCKET_NAME']
    destination_bucket_name = current_app.config['LETTERS_PDF_BUCKET_NAME']
    conn = boto3.resource('s3', region_name='eu-west-1')
    conn.create_bucket(
        Bucket=scan_bucket_name,
        CreateBucketConfiguration={'LocationConstraint': 'eu-west-1'}
    )
    conn.create_bucket(
        Bucket=template_preview_bucket_name,
        CreateBucketConfiguration={'LocationConstraint': 'eu-west-1'}
    )
    conn.create_bucket(
        Bucket=destination_bucket_name,
        CreateBucketConfiguration={'LocationConstraint': 'eu-west-1'}
    )

    s3 = boto3.client('s3', region_name='eu-west-1')
    s3.put_object(Bucket=scan_bucket_name, Key=filename, Body=b'original_pdf_content')
    s3.put_object(Bucket=template_preview_bucket_name, Key=filename, Body=b'sanitised_pdf_content')

    sample_letter_notification.status = NOTIFICATION_PENDING_VIRUS_CHECK
    sample_letter_notification.billable_units = 1
    sample_letter_notification.created_at = datetime(2018, 7, 1, 12)

    encrypted_data = encryption.encrypt({
        'page_count': 2,
        'message': None,
        'invalid_pages': None,
        'validation_status': 'passed',
        'filename': filename,
        'notification_id': str(sample_letter_notification.id),
        'address': address
    })
    process_sanitised_letter(encrypted_data)

    assert sample_letter_notification.status == 'created'
    assert sample_letter_notification.billable_units == 1
    assert sample_letter_notification.to == address
    assert sample_letter_notification.postage == expected_postage
    assert sample_letter_notification.international == expected_international


@mock_s3
@pytest.mark.parametrize('key_type', [KEY_TYPE_NORMAL, KEY_TYPE_TEST])
def test_process_sanitised_letter_with_invalid_letter(sample_letter_notification, key_type):
    filename = 'NOTIFY.{}'.format(sample_letter_notification.reference)

    scan_bucket_name = current_app.config['LETTERS_SCAN_BUCKET_NAME']
    template_preview_bucket_name = current_app.config['LETTER_SANITISE_BUCKET_NAME']
    invalid_letter_bucket_name = current_app.config['INVALID_PDF_BUCKET_NAME']
    conn = boto3.resource('s3', region_name='eu-west-1')

    scan_bucket = conn.create_bucket(
        Bucket=scan_bucket_name,
        CreateBucketConfiguration={'LocationConstraint': 'eu-west-1'}
    )
    template_preview_bucket = conn.create_bucket(
        Bucket=template_preview_bucket_name,
        CreateBucketConfiguration={'LocationConstraint': 'eu-west-1'}
    )
    invalid_letter_bucket = conn.create_bucket(
        Bucket=invalid_letter_bucket_name,
        CreateBucketConfiguration={'LocationConstraint': 'eu-west-1'}
    )

    s3 = boto3.client('s3', region_name='eu-west-1')
    s3.put_object(Bucket=scan_bucket_name, Key=filename, Body=b'original_pdf_content')

    sample_letter_notification.status = NOTIFICATION_PENDING_VIRUS_CHECK
    sample_letter_notification.key_type = key_type
    sample_letter_notification.billable_units = 1
    sample_letter_notification.created_at = datetime(2018, 7, 1, 12)

    encrypted_data = encryption.encrypt({
        'page_count': 2,
        'message': 'content-outside-printable-area',
        'invalid_pages': [1],
        'validation_status': 'failed',
        'filename': filename,
        'notification_id': str(sample_letter_notification.id),
        'address': None,
    })
    process_sanitised_letter(encrypted_data)

    assert sample_letter_notification.status == NOTIFICATION_VALIDATION_FAILED
    assert sample_letter_notification.billable_units == 0

    assert not [x for x in scan_bucket.objects.all()]
    assert not [x for x in template_preview_bucket.objects.all()]
    assert len([x for x in invalid_letter_bucket.objects.all()]) == 1

    file_contents = conn.Object(invalid_letter_bucket_name, filename).get()['Body'].read().decode('utf-8')
    assert file_contents == 'original_pdf_content'


def test_process_sanitised_letter_when_letter_status_is_not_pending_virus_scan(
    sample_letter_notification,
    mocker,
):
    mock_s3 = mocker.patch('app.celery.letters_pdf_tasks.s3')
    sample_letter_notification.status = NOTIFICATION_CREATED

    encrypted_data = encryption.encrypt({
        'page_count': 2,
        'message': None,
        'invalid_pages': None,
        'validation_status': 'passed',
        'filename': 'NOTIFY.{}'.format(sample_letter_notification.reference),
        'notification_id': str(sample_letter_notification.id),
        'address': None
    })
    process_sanitised_letter(encrypted_data)

    assert not mock_s3.called


def test_process_sanitised_letter_puts_letter_into_tech_failure_for_boto_errors(
    sample_letter_notification,
    mocker,
):
    mocker.patch('app.celery.letters_pdf_tasks.s3.get_s3_object', side_effect=ClientError({}, 'operation_name'))
    sample_letter_notification.status = NOTIFICATION_PENDING_VIRUS_CHECK

    encrypted_data = encryption.encrypt({
        'page_count': 2,
        'message': None,
        'invalid_pages': None,
        'validation_status': 'passed',
        'filename': 'NOTIFY.{}'.format(sample_letter_notification.reference),
        'notification_id': str(sample_letter_notification.id),
        'address': None
    })

    with pytest.raises(NotificationTechnicalFailureException):
        process_sanitised_letter(encrypted_data)

    assert sample_letter_notification.status == NOTIFICATION_TECHNICAL_FAILURE


def test_process_sanitised_letter_retries_if_there_is_an_exception(
    mocker,
    sample_letter_notification,
):
    mocker.patch('app.celery.letters_pdf_tasks.update_letter_pdf_status', side_effect=Exception())
    mock_celery_retry = mocker.patch('app.celery.letters_pdf_tasks.process_sanitised_letter.retry')

    sample_letter_notification.status = NOTIFICATION_PENDING_VIRUS_CHECK
    encrypted_data = encryption.encrypt({
        'page_count': 2,
        'message': None,
        'invalid_pages': None,
        'validation_status': 'passed',
        'filename': 'NOTIFY.{}'.format(sample_letter_notification.reference),
        'notification_id': str(sample_letter_notification.id),
        'address': None
    })

    process_sanitised_letter(encrypted_data)

    mock_celery_retry.assert_called_once_with(queue='retry-tasks')


def test_process_sanitised_letter_puts_letter_into_technical_failure_if_max_retries_exceeded(
    mocker,
    sample_letter_notification,
):
    mocker.patch('app.celery.letters_pdf_tasks.update_letter_pdf_status', side_effect=Exception())
    mocker.patch('app.celery.letters_pdf_tasks.process_sanitised_letter.retry', side_effect=MaxRetriesExceededError())

    sample_letter_notification.status = NOTIFICATION_PENDING_VIRUS_CHECK
    encrypted_data = encryption.encrypt({
        'page_count': 2,
        'message': None,
        'invalid_pages': None,
        'validation_status': 'passed',
        'filename': 'NOTIFY.{}'.format(sample_letter_notification.reference),
        'notification_id': str(sample_letter_notification.id),
        'address': None
    })

    with pytest.raises(NotificationTechnicalFailureException):
        process_sanitised_letter(encrypted_data)

    assert sample_letter_notification.status == NOTIFICATION_TECHNICAL_FAILURE


def test_process_letter_task_check_virus_scan_failed(sample_letter_notification, mocker):
    filename = 'NOTIFY.{}'.format(sample_letter_notification.reference)
    sample_letter_notification.status = NOTIFICATION_PENDING_VIRUS_CHECK
    mock_move_failed_pdf = mocker.patch('app.celery.letters_pdf_tasks.move_failed_pdf')

    with pytest.raises(VirusScanError) as e:
        process_virus_scan_failed(filename)

    assert "Virus scan failed:" in str(e.value)
    mock_move_failed_pdf.assert_called_once_with(filename, ScanErrorType.FAILURE)
    assert sample_letter_notification.status == NOTIFICATION_VIRUS_SCAN_FAILED


def test_process_letter_task_check_virus_scan_error(sample_letter_notification, mocker):
    filename = 'NOTIFY.{}'.format(sample_letter_notification.reference)
    sample_letter_notification.status = NOTIFICATION_PENDING_VIRUS_CHECK
    mock_move_failed_pdf = mocker.patch('app.celery.letters_pdf_tasks.move_failed_pdf')

    with pytest.raises(VirusScanError) as e:
        process_virus_scan_error(filename)

    assert "Virus scan error:" in str(e.value)
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


@pytest.mark.parametrize('permissions, expected_international_letters_allowed', (
    ([LETTER_TYPE], False),
    ([LETTER_TYPE, INTERNATIONAL_LETTERS], True),
))
def test_resanitise_pdf_calls_template_preview_with_letter_details(
    mocker,
    sample_letter_notification,
    permissions,
    expected_international_letters_allowed,
):
    mock_celery = mocker.patch('app.celery.letters_pdf_tasks.notify_celery.send_task')

    sample_letter_notification.created_at = datetime(2021, 2, 7, 12)
    sample_letter_notification.service = create_service(
        service_permissions=permissions
    )

    resanitise_pdf(sample_letter_notification.id)

    mock_celery.assert_called_once_with(
        name=TaskNames.RECREATE_PDF_FOR_PRECOMPILED_LETTER,
        kwargs={
            'notification_id': str(sample_letter_notification.id),
            'file_location': '2021-02-07/NOTIFY.FOO.D.2.C.20210207120000.PDF',
            'allow_international_letters': expected_international_letters_allowed,
        },
        queue=QueueNames.SANITISE_LETTERS,
    )
