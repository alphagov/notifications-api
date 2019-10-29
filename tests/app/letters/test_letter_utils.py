import pytest
from datetime import datetime

import boto3
from flask import current_app
from freezegun import freeze_time
from moto import mock_s3

from app.letters.utils import (
    copy_redaction_failed_pdf,
    get_bucket_name_and_prefix_for_notification,
    get_letter_pdf_filename,
    get_letter_pdf_and_metadata,
    letter_print_day,
    upload_letter_pdf,
    ScanErrorType, move_failed_pdf, get_folder_name
)
from app.models import KEY_TYPE_NORMAL, KEY_TYPE_TEST, PRECOMPILED_TEMPLATE_NAME, NOTIFICATION_VALIDATION_FAILED
from tests.app.db import create_notification

FROZEN_DATE_TIME = "2018-03-14 17:00:00"


@pytest.fixture(name='sample_precompiled_letter_notification')
def _sample_precompiled_letter_notification(sample_letter_notification):
    sample_letter_notification.template.hidden = True
    sample_letter_notification.template.name = PRECOMPILED_TEMPLATE_NAME
    sample_letter_notification.reference = 'foo'
    with freeze_time(FROZEN_DATE_TIME):
        sample_letter_notification.created_at = datetime.utcnow()
        sample_letter_notification.updated_at = datetime.utcnow()
    return sample_letter_notification


@pytest.fixture(name='sample_precompiled_letter_notification_using_test_key')
def _sample_precompiled_letter_notification_using_test_key(sample_precompiled_letter_notification):
    sample_precompiled_letter_notification.key_type = KEY_TYPE_TEST
    return sample_precompiled_letter_notification


@pytest.mark.parametrize('created_at,folder', [
    (datetime(2017, 1, 1, 17, 29), '2017-01-01'),
    (datetime(2017, 1, 1, 17, 31), '2017-01-02'),
])
def test_get_bucket_name_and_prefix_for_notification_valid_notification(sample_notification, created_at, folder):
    sample_notification.created_at = created_at
    sample_notification.updated_at = created_at

    bucket, bucket_prefix = get_bucket_name_and_prefix_for_notification(sample_notification)

    assert bucket == current_app.config['LETTERS_PDF_BUCKET_NAME']
    assert bucket_prefix == '{folder}/NOTIFY.{reference}'.format(
        folder=folder,
        reference=sample_notification.reference
    ).upper()


def test_get_bucket_name_and_prefix_for_notification_is_tomorrow_after_17_30(sample_notification):
    sample_notification.created_at = datetime(2019, 8, 1, 17, 35)
    sample_notification.sent_at = datetime(2019, 8, 2, 17, 45)

    bucket, bucket_prefix = get_bucket_name_and_prefix_for_notification(sample_notification)

    assert bucket == current_app.config['LETTERS_PDF_BUCKET_NAME']
    assert bucket_prefix == '{folder}/NOTIFY.{reference}'.format(
        folder='2019-08-02',
        reference=sample_notification.reference
    ).upper()


def test_get_bucket_name_and_prefix_for_notification_is_today_before_17_30(sample_notification):
    sample_notification.created_at = datetime(2019, 8, 1, 12, 00)
    sample_notification.updated_at = datetime(2019, 8, 2, 12, 00)
    sample_notification.sent_at = datetime(2019, 8, 3, 12, 00)

    bucket, bucket_prefix = get_bucket_name_and_prefix_for_notification(sample_notification)

    assert bucket == current_app.config['LETTERS_PDF_BUCKET_NAME']
    assert bucket_prefix == '{folder}/NOTIFY.{reference}'.format(
        folder='2019-08-01',
        reference=sample_notification.reference
    ).upper()


@freeze_time(FROZEN_DATE_TIME)
def test_get_bucket_name_and_prefix_for_notification_precompiled_letter_using_test_key(
    sample_precompiled_letter_notification_using_test_key
):
    bucket, bucket_prefix = get_bucket_name_and_prefix_for_notification(
        sample_precompiled_letter_notification_using_test_key)

    assert bucket == current_app.config['TEST_LETTERS_BUCKET_NAME']
    assert bucket_prefix == 'NOTIFY.{}'.format(
        sample_precompiled_letter_notification_using_test_key.reference).upper()


@freeze_time(FROZEN_DATE_TIME)
def test_get_bucket_name_and_prefix_for_notification_templated_letter_using_test_key(sample_letter_notification):
    sample_letter_notification.key_type = KEY_TYPE_TEST

    bucket, bucket_prefix = get_bucket_name_and_prefix_for_notification(sample_letter_notification)

    assert bucket == current_app.config['TEST_LETTERS_BUCKET_NAME']
    assert bucket_prefix == 'NOTIFY.{}'.format(sample_letter_notification.reference).upper()


@freeze_time(FROZEN_DATE_TIME)
def test_get_bucket_name_and_prefix_for_failed_validation(sample_precompiled_letter_notification):
    sample_precompiled_letter_notification.status = NOTIFICATION_VALIDATION_FAILED
    bucket, bucket_prefix = get_bucket_name_and_prefix_for_notification(sample_precompiled_letter_notification)

    assert bucket == current_app.config['INVALID_PDF_BUCKET_NAME']
    assert bucket_prefix == 'NOTIFY.{}'.format(
        sample_precompiled_letter_notification.reference).upper()


@freeze_time(FROZEN_DATE_TIME)
def test_get_bucket_name_and_prefix_for_test_noti_with_failed_validation(
    sample_precompiled_letter_notification_using_test_key
):
    sample_precompiled_letter_notification_using_test_key.status = NOTIFICATION_VALIDATION_FAILED
    bucket, bucket_prefix = get_bucket_name_and_prefix_for_notification(
        sample_precompiled_letter_notification_using_test_key
    )

    assert bucket == current_app.config['INVALID_PDF_BUCKET_NAME']
    assert bucket_prefix == 'NOTIFY.{}'.format(
        sample_precompiled_letter_notification_using_test_key.reference).upper()


def test_get_bucket_name_and_prefix_for_notification_invalid_notification():
    with pytest.raises(AttributeError):
        get_bucket_name_and_prefix_for_notification(None)


@pytest.mark.parametrize('crown_flag,expected_crown_text', [
    (True, 'C'),
    (False, 'N'),
])
def test_get_letter_pdf_filename_returns_correct_filename(
        notify_api, mocker, crown_flag, expected_crown_text):
    sending_date = datetime(2017, 12, 4, 17, 29)
    filename = get_letter_pdf_filename(reference='foo', crown=crown_flag, sending_date=sending_date)

    assert filename == '2017-12-04/NOTIFY.FOO.D.2.C.{}.20171204172900.PDF'.format(expected_crown_text)


@pytest.mark.parametrize('postage,expected_postage', [
    ('second', 2),
    ('first', 1),
])
def test_get_letter_pdf_filename_returns_correct_postage_for_filename(
        notify_api, postage, expected_postage):
    sending_date = datetime(2017, 12, 4, 17, 29)
    filename = get_letter_pdf_filename(reference='foo', crown=True, sending_date=sending_date, postage=postage)

    assert filename == '2017-12-04/NOTIFY.FOO.D.{}.C.C.20171204172900.PDF'.format(expected_postage)


def test_get_letter_pdf_filename_returns_correct_filename_for_test_letters(
        notify_api, mocker):
    sending_date = datetime(2017, 12, 4, 17, 29)
    filename = get_letter_pdf_filename(reference='foo', crown='C',
                                       sending_date=sending_date, dont_use_sending_date=True)

    assert filename == 'NOTIFY.FOO.D.2.C.C.20171204172900.PDF'


def test_get_letter_pdf_filename_returns_tomorrows_filename(notify_api, mocker):
    sending_date = datetime(2017, 12, 4, 17, 31)
    filename = get_letter_pdf_filename(reference='foo', crown=True, sending_date=sending_date)

    assert filename == '2017-12-05/NOTIFY.FOO.D.2.C.C.20171204173100.PDF'


@mock_s3
@pytest.mark.parametrize('bucket_config_name,filename_format', [
    ('TEST_LETTERS_BUCKET_NAME', 'NOTIFY.FOO.D.2.C.C.%Y%m%d%H%M%S.PDF'),
    ('LETTERS_PDF_BUCKET_NAME', '%Y-%m-%d/NOTIFY.FOO.D.2.C.C.%Y%m%d%H%M%S.PDF')
])
@freeze_time(FROZEN_DATE_TIME)
def test_get_letter_pdf_gets_pdf_from_correct_bucket(
    sample_precompiled_letter_notification_using_test_key,
    bucket_config_name,
    filename_format
):
    if bucket_config_name == 'LETTERS_PDF_BUCKET_NAME':
        sample_precompiled_letter_notification_using_test_key.key_type = KEY_TYPE_NORMAL

    bucket_name = current_app.config[bucket_config_name]
    filename = datetime.utcnow().strftime(filename_format)
    conn = boto3.resource('s3', region_name='eu-west-1')
    conn.create_bucket(Bucket=bucket_name)
    s3 = boto3.client('s3', region_name='eu-west-1')
    s3.put_object(Bucket=bucket_name, Key=filename, Body=b'pdf_content')

    file_data, metadata = get_letter_pdf_and_metadata(sample_precompiled_letter_notification_using_test_key)

    assert file_data == b'pdf_content'


@pytest.mark.parametrize('is_precompiled_letter,bucket_config_name', [
    (False, 'LETTERS_PDF_BUCKET_NAME'),
    (True, 'LETTERS_SCAN_BUCKET_NAME')
])
def test_upload_letter_pdf_to_correct_bucket(
    sample_letter_notification, mocker, is_precompiled_letter, bucket_config_name
):
    if is_precompiled_letter:
        sample_letter_notification.template.hidden = True
        sample_letter_notification.template.name = PRECOMPILED_TEMPLATE_NAME

    mock_s3 = mocker.patch('app.letters.utils.s3upload')

    filename = get_letter_pdf_filename(
        reference=sample_letter_notification.reference,
        crown=sample_letter_notification.service.crown,
        sending_date=sample_letter_notification.created_at,
        dont_use_sending_date=is_precompiled_letter
    )

    upload_letter_pdf(sample_letter_notification, b'\x00\x01', precompiled=is_precompiled_letter)

    mock_s3.assert_called_once_with(
        bucket_name=current_app.config[bucket_config_name],
        file_location=filename,
        filedata=b'\x00\x01',
        region=current_app.config['AWS_REGION']
    )


@pytest.mark.parametrize('postage,expected_postage', [
    ('second', 2),
    ('first', 1)
])
def test_upload_letter_pdf_uses_postage_from_notification(
    sample_letter_template, mocker, postage, expected_postage
):
    letter_notification = create_notification(template=sample_letter_template, postage=postage)
    mock_s3 = mocker.patch('app.letters.utils.s3upload')

    filename = get_letter_pdf_filename(
        reference=letter_notification.reference,
        crown=letter_notification.service.crown,
        sending_date=letter_notification.created_at,
        dont_use_sending_date=False,
        postage=letter_notification.postage
    )

    upload_letter_pdf(letter_notification, b'\x00\x01', precompiled=False)

    mock_s3.assert_called_once_with(
        bucket_name=current_app.config['LETTERS_PDF_BUCKET_NAME'],
        file_location=filename,
        filedata=b'\x00\x01',
        region=current_app.config['AWS_REGION']
    )


@mock_s3
@freeze_time(FROZEN_DATE_TIME)
def test_move_failed_pdf_error(notify_api):
    filename = 'test.pdf'
    bucket_name = current_app.config['LETTERS_SCAN_BUCKET_NAME']

    conn = boto3.resource('s3', region_name='eu-west-1')
    bucket = conn.create_bucket(Bucket=bucket_name)

    s3 = boto3.client('s3', region_name='eu-west-1')
    s3.put_object(Bucket=bucket_name, Key=filename, Body=b'pdf_content')

    move_failed_pdf(filename, ScanErrorType.ERROR)

    assert 'ERROR/' + filename in [o.key for o in bucket.objects.all()]
    assert filename not in [o.key for o in bucket.objects.all()]


@mock_s3
@freeze_time(FROZEN_DATE_TIME)
def test_move_failed_pdf_scan_failed(notify_api):
    filename = 'test.pdf'
    bucket_name = current_app.config['LETTERS_SCAN_BUCKET_NAME']

    conn = boto3.resource('s3', region_name='eu-west-1')
    bucket = conn.create_bucket(Bucket=bucket_name)

    s3 = boto3.client('s3', region_name='eu-west-1')
    s3.put_object(Bucket=bucket_name, Key=filename, Body=b'pdf_content')

    move_failed_pdf(filename, ScanErrorType.FAILURE)

    assert 'FAILURE/' + filename in [o.key for o in bucket.objects.all()]
    assert filename not in [o.key for o in bucket.objects.all()]


@mock_s3
@freeze_time(FROZEN_DATE_TIME)
def test_copy_redaction_failed_pdf(notify_api):
    filename = 'test.pdf'
    bucket_name = current_app.config['LETTERS_SCAN_BUCKET_NAME']

    conn = boto3.resource('s3', region_name='eu-west-1')
    bucket = conn.create_bucket(Bucket=bucket_name)

    s3 = boto3.client('s3', region_name='eu-west-1')
    s3.put_object(Bucket=bucket_name, Key=filename, Body=b'pdf_content')

    copy_redaction_failed_pdf(filename)

    assert 'REDACTION_FAILURE/' + filename in [o.key for o in bucket.objects.all()]
    assert filename in [o.key for o in bucket.objects.all()]


@pytest.mark.parametrize("freeze_date, expected_folder_name",
                         [("2018-04-01 17:50:00", "2018-04-02/"),
                          ("2018-07-02 16:29:00", "2018-07-02/"),
                          ("2018-07-02 16:30:00", "2018-07-02/"),
                          ("2018-07-02 16:31:00", "2018-07-03/"),
                          ("2018-01-02 16:31:00", "2018-01-02/"),
                          ("2018-01-02 17:31:00", "2018-01-03/"),

                          ("2018-07-02 22:30:00", "2018-07-03/"),
                          ("2018-07-02 23:30:00", "2018-07-03/"),
                          ("2018-07-03 00:30:00", "2018-07-03/"),

                          ("2018-01-02 22:30:00", "2018-01-03/"),
                          ("2018-01-02 23:30:00", "2018-01-03/"),
                          ("2018-01-03 00:30:00", "2018-01-03/"),
                          ])
def test_get_folder_name_in_british_summer_time(notify_api, freeze_date, expected_folder_name):
    with freeze_time(freeze_date):
        now = datetime.utcnow()
        folder_name = get_folder_name(_now=now, dont_use_sending_date=False)
    assert folder_name == expected_folder_name


def test_get_folder_name_returns_empty_string_for_test_letter():
    assert '' == get_folder_name(datetime.utcnow(), dont_use_sending_date=True)


@freeze_time('2017-07-07 20:00:00')
def test_letter_print_day_returns_today_if_letter_was_printed_after_1730_yesterday():
    created_at = datetime(2017, 7, 6, 17, 30)
    assert letter_print_day(created_at) == 'today'


@freeze_time('2017-07-07 16:30:00')
def test_letter_print_day_returns_today_if_letter_was_printed_today():
    created_at = datetime(2017, 7, 7, 12, 0)
    assert letter_print_day(created_at) == 'today'


@pytest.mark.parametrize('created_at, formatted_date', [
    (datetime(2017, 7, 5, 16, 30), 'on 6 July'),
    (datetime(2017, 7, 6, 16, 29), 'on 6 July'),
    (datetime(2016, 8, 8, 10, 00), 'on 8 August'),
    (datetime(2016, 12, 12, 17, 29), 'on 12 December'),
    (datetime(2016, 12, 12, 17, 30), 'on 13 December'),
])
@freeze_time('2017-07-07 16:30:00')
def test_letter_print_day_returns_formatted_date_if_letter_printed_before_1730_yesterday(created_at, formatted_date):
    assert letter_print_day(created_at) == formatted_date
