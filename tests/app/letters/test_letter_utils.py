import pytest
from datetime import datetime

import boto3
from flask import current_app
from freezegun import freeze_time
from moto import mock_s3

from app.letters.utils import (
    get_bucket_prefix_for_notification,
    get_letter_pdf_filename,
    get_letter_pdf,
    upload_letter_pdf,
    move_scanned_pdf_to_letters_pdf_bucket
)
from app.models import KEY_TYPE_NORMAL, KEY_TYPE_TEST, PRECOMPILED_TEMPLATE_NAME
from app.variables import Retention

FROZEN_DATE_TIME = "2018-03-14 17:00:00"


@pytest.fixture()
@freeze_time(FROZEN_DATE_TIME)
def sample_precompiled_letter_notification_using_test_key(sample_letter_notification):
    sample_letter_notification.template.hidden = True
    sample_letter_notification.template.name = PRECOMPILED_TEMPLATE_NAME
    sample_letter_notification.key_type = KEY_TYPE_TEST
    sample_letter_notification.reference = 'foo'
    sample_letter_notification.created_at = datetime.utcnow()
    return sample_letter_notification


def test_get_bucket_prefix_for_notification_valid_notification(sample_notification):

    bucket_prefix = get_bucket_prefix_for_notification(sample_notification)

    assert bucket_prefix == '{folder}/NOTIFY.{reference}'.format(
        folder=sample_notification.created_at.date(),
        reference=sample_notification.reference
    ).upper()


@freeze_time(FROZEN_DATE_TIME)
def test_get_bucket_prefix_for_notification_precompiled_letter_using_test_key(
    sample_precompiled_letter_notification_using_test_key
):
    bucket_prefix = get_bucket_prefix_for_notification(
        sample_precompiled_letter_notification_using_test_key, is_test_letter=True)

    assert bucket_prefix == 'NOTIFY.{}'.format(
        sample_precompiled_letter_notification_using_test_key.reference).upper()


def test_get_bucket_prefix_for_notification_invalid_notification():
    with pytest.raises(AttributeError):
        get_bucket_prefix_for_notification(None)


@pytest.mark.parametrize('crown_flag,expected_crown_text', [
    (True, 'C'),
    (False, 'N'),
])
@freeze_time("2017-12-04 17:29:00")
def test_get_letter_pdf_filename_returns_correct_filename(
        notify_api, mocker, crown_flag, expected_crown_text):
    filename = get_letter_pdf_filename(reference='foo', crown=crown_flag)

    assert filename == '2017-12-04/NOTIFY.FOO.D.2.C.{}.20171204172900.PDF'.format(expected_crown_text)


@freeze_time("2017-12-04 17:29:00")
def test_get_letter_pdf_filename_returns_correct_filename_for_test_letters(
        notify_api, mocker):
    filename = get_letter_pdf_filename(reference='foo', crown='C', is_test_or_scan_letter=True)

    assert filename == 'NOTIFY.FOO.D.2.C.C.20171204172900.PDF'


@freeze_time("2017-12-04 17:31:00")
def test_get_letter_pdf_filename_returns_tomorrows_filename(notify_api, mocker):
    filename = get_letter_pdf_filename(reference='foo', crown=True)

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

    ret = get_letter_pdf(sample_precompiled_letter_notification_using_test_key)

    assert ret == b'pdf_content'


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
        is_test_or_scan_letter=is_precompiled_letter
    )

    upload_letter_pdf(sample_letter_notification, b'\x00\x01')

    mock_s3.assert_called_once_with(
        bucket_name=current_app.config[bucket_config_name],
        file_location=filename,
        filedata=b'\x00\x01',
        region=current_app.config['AWS_REGION'],
        tags={Retention.KEY: Retention.ONE_WEEK}
    )


@mock_s3
@freeze_time(FROZEN_DATE_TIME)
def test_move_scanned_letter_pdf_to_processing_bucket(notify_api):
    filename = 'test.pdf'
    source_bucket_name = current_app.config['LETTERS_SCAN_BUCKET_NAME']
    target_bucket_name = current_app.config['LETTERS_PDF_BUCKET_NAME']

    conn = boto3.resource('s3', region_name='eu-west-1')
    source_bucket = conn.create_bucket(Bucket=source_bucket_name)
    target_bucket = conn.create_bucket(Bucket=target_bucket_name)

    s3 = boto3.client('s3', region_name='eu-west-1')
    s3.put_object(Bucket=source_bucket_name, Key=filename, Body=b'pdf_content')

    move_scanned_pdf_to_letters_pdf_bucket(filename)

    assert '2018-03-14/' + filename in [o.key for o in target_bucket.objects.all()]
    assert filename not in [o.key for o in source_bucket.objects.all()]
