from datetime import datetime, timedelta
from enum import Enum

import boto3
from flask import current_app

from notifications_utils.letter_timings import LETTER_PROCESSING_DEADLINE
from notifications_utils.s3 import s3upload
from notifications_utils.timezones import convert_utc_to_bst

from app.models import KEY_TYPE_TEST, SECOND_CLASS, RESOLVE_POSTAGE_FOR_FILE_NAME, NOTIFICATION_VALIDATION_FAILED


class ScanErrorType(Enum):
    ERROR = 1
    FAILURE = 2


LETTERS_PDF_FILE_LOCATION_STRUCTURE = \
    '{folder}NOTIFY.{reference}.{duplex}.{letter_class}.{colour}.{crown}.{date}.pdf'

PRECOMPILED_BUCKET_PREFIX = '{folder}NOTIFY.{reference}'


def get_folder_name(_now, is_test_or_scan_letter=False):
    if is_test_or_scan_letter:
        folder_name = ''
    else:
        print_datetime = convert_utc_to_bst(_now)
        if print_datetime.time() > LETTER_PROCESSING_DEADLINE:
            print_datetime += timedelta(days=1)
        folder_name = '{}/'.format(print_datetime.date())
    return folder_name


def get_letter_pdf_filename(reference, crown, is_scan_letter=False, postage=SECOND_CLASS):
    now = datetime.utcnow()

    upload_file_name = LETTERS_PDF_FILE_LOCATION_STRUCTURE.format(
        folder=get_folder_name(now, is_scan_letter),
        reference=reference,
        duplex="D",
        letter_class=RESOLVE_POSTAGE_FOR_FILE_NAME[postage],
        colour="C",
        crown="C" if crown else "N",
        date=now.strftime('%Y%m%d%H%M%S')
    ).upper()

    return upload_file_name


def get_bucket_name_and_prefix_for_notification(notification):
    is_test_letter = notification.key_type == KEY_TYPE_TEST and notification.template.is_precompiled_letter
    folder = ''
    if notification.status == NOTIFICATION_VALIDATION_FAILED:
        bucket_name = current_app.config['INVALID_PDF_BUCKET_NAME']
    elif is_test_letter:
        bucket_name = current_app.config['TEST_LETTERS_BUCKET_NAME']
    else:
        bucket_name = current_app.config['LETTERS_PDF_BUCKET_NAME']
        folder = get_folder_name(notification.created_at, False)

    upload_file_name = PRECOMPILED_BUCKET_PREFIX.format(
        folder=folder,
        reference=notification.reference
    ).upper()

    return bucket_name, upload_file_name


def get_reference_from_filename(filename):
    # filename looks like '2018-01-13/NOTIFY.ABCDEF1234567890.D.2.C.C.20180113120000.PDF'
    filename_parts = filename.split('.')
    return filename_parts[1]


def upload_letter_pdf(notification, pdf_data, precompiled=False):
    current_app.logger.info("PDF Letter {} reference {} created at {}, {} bytes".format(
        notification.id, notification.reference, notification.created_at, len(pdf_data)))

    upload_file_name = get_letter_pdf_filename(
        notification.reference,
        notification.service.crown,
        is_scan_letter=precompiled,
        postage=notification.postage
    )

    if precompiled:
        bucket_name = current_app.config['LETTERS_SCAN_BUCKET_NAME']
    else:
        bucket_name = current_app.config['LETTERS_PDF_BUCKET_NAME']

    s3upload(
        filedata=pdf_data,
        region=current_app.config['AWS_REGION'],
        bucket_name=bucket_name,
        file_location=upload_file_name
    )

    current_app.logger.info("Uploaded letters PDF {} to {} for notification id {}".format(
        upload_file_name, bucket_name, notification.id))
    return upload_file_name


def move_failed_pdf(source_filename, scan_error_type):
    scan_bucket = current_app.config['LETTERS_SCAN_BUCKET_NAME']

    target_filename = ('ERROR/' if scan_error_type == ScanErrorType.ERROR else 'FAILURE/') + source_filename

    _move_s3_object(scan_bucket, source_filename, scan_bucket, target_filename)


def move_error_pdf_to_scan_bucket(source_filename):
    scan_bucket = current_app.config['LETTERS_SCAN_BUCKET_NAME']
    error_file = 'ERROR/' + source_filename

    _move_s3_object(scan_bucket, error_file, scan_bucket, source_filename)


def move_scan_to_invalid_pdf_bucket(source_filename):
    scan_bucket = current_app.config['LETTERS_SCAN_BUCKET_NAME']
    invalid_pdf_bucket = current_app.config['INVALID_PDF_BUCKET_NAME']
    _move_s3_object(scan_bucket, source_filename, invalid_pdf_bucket, source_filename)


def get_file_names_from_error_bucket():
    s3 = boto3.resource('s3')
    scan_bucket = current_app.config['LETTERS_SCAN_BUCKET_NAME']
    bucket = s3.Bucket(scan_bucket)

    return bucket.objects.filter(Prefix="ERROR")


def get_letter_pdf(notification):
    bucket_name, prefix = get_bucket_name_and_prefix_for_notification(notification)

    s3 = boto3.resource('s3')
    bucket = s3.Bucket(bucket_name)

    item = next(x for x in bucket.objects.filter(Prefix=prefix))

    obj = s3.Object(
        bucket_name=bucket_name,
        key=item.key
    )
    return obj.get()["Body"].read()


def _move_s3_object(source_bucket, source_filename, target_bucket, target_filename):
    s3 = boto3.resource('s3')
    copy_source = {'Bucket': source_bucket, 'Key': source_filename}

    target_bucket = s3.Bucket(target_bucket)
    obj = target_bucket.Object(target_filename)

    # Tags are copied across but the expiration time is reset in the destination bucket
    # e.g. if a file has 5 days left to expire on a ONE_WEEK retention in the source bucket,
    # in the destination bucket the expiration time will be reset to 7 days left to expire
    obj.copy(copy_source, ExtraArgs={'ServerSideEncryption': 'AES256'})

    s3.Object(source_bucket, source_filename).delete()

    current_app.logger.info("Moved letter PDF: {}/{} to {}/{}".format(
        source_bucket, source_filename, target_bucket, target_filename))


def letter_print_day(created_at):
    bst_print_datetime = convert_utc_to_bst(created_at) + timedelta(hours=6, minutes=30)
    bst_print_date = bst_print_datetime.date()

    current_bst_date = convert_utc_to_bst(datetime.utcnow()).date()

    if bst_print_date >= current_bst_date:
        return 'today'
    else:
        print_date = bst_print_datetime.strftime('%d %B').lstrip('0')
        return 'on {}'.format(print_date)
