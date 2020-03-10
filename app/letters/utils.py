import boto3
import io
import json
import math

from app.models import KEY_TYPE_TEST, SECOND_CLASS, RESOLVE_POSTAGE_FOR_FILE_NAME, NOTIFICATION_VALIDATION_FAILED

from datetime import datetime, timedelta
from enum import Enum

from flask import current_app

from notifications_utils.letter_timings import LETTER_PROCESSING_DEADLINE
from notifications_utils.pdf import pdf_page_count
from notifications_utils.s3 import s3upload
from notifications_utils.timezones import convert_utc_to_bst


class ScanErrorType(Enum):
    ERROR = 1
    FAILURE = 2


LETTERS_PDF_FILE_LOCATION_STRUCTURE = \
    '{folder}NOTIFY.{reference}.{duplex}.{letter_class}.{colour}.{crown}.{date}.pdf'

PRECOMPILED_BUCKET_PREFIX = '{folder}NOTIFY.{reference}'


def get_folder_name(_now, *, dont_use_sending_date=False):
    if dont_use_sending_date:
        folder_name = ''
    else:
        print_datetime = convert_utc_to_bst(_now)
        if print_datetime.time() > LETTER_PROCESSING_DEADLINE:
            print_datetime += timedelta(days=1)
        folder_name = '{}/'.format(print_datetime.date())
    return folder_name


def get_letter_pdf_filename(reference, crown, sending_date, dont_use_sending_date=False, postage=SECOND_CLASS):
    upload_file_name = LETTERS_PDF_FILE_LOCATION_STRUCTURE.format(
        folder=get_folder_name(sending_date, dont_use_sending_date=dont_use_sending_date),
        reference=reference,
        duplex="D",
        letter_class=RESOLVE_POSTAGE_FOR_FILE_NAME[postage],
        colour="C",
        crown="C" if crown else "N",
        date=sending_date.strftime('%Y%m%d%H%M%S')
    ).upper()
    return upload_file_name


def get_bucket_name_and_prefix_for_notification(notification):
    folder = ''
    if notification.status == NOTIFICATION_VALIDATION_FAILED:
        bucket_name = current_app.config['INVALID_PDF_BUCKET_NAME']
    elif notification.key_type == KEY_TYPE_TEST:
        bucket_name = current_app.config['TEST_LETTERS_BUCKET_NAME']
    else:
        bucket_name = current_app.config['LETTERS_PDF_BUCKET_NAME']
        folder = get_folder_name(notification.created_at, dont_use_sending_date=False)

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
        reference=notification.reference,
        crown=notification.service.crown,
        sending_date=notification.created_at,
        dont_use_sending_date=precompiled or notification.key_type == KEY_TYPE_TEST,
        postage=notification.postage
    )

    if precompiled:
        bucket_name = current_app.config['LETTERS_SCAN_BUCKET_NAME']
    elif notification.key_type == KEY_TYPE_TEST:
        bucket_name = current_app.config['TEST_LETTERS_BUCKET_NAME']
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


def move_scan_to_invalid_pdf_bucket(source_filename, message=None, invalid_pages=None, page_count=None):
    metadata = {}
    if message:
        metadata["message"] = message
    if invalid_pages:
        metadata["invalid_pages"] = json.dumps(invalid_pages)
    if page_count:
        metadata["page_count"] = str(page_count)

    _move_s3_object(
        source_bucket=current_app.config['LETTERS_SCAN_BUCKET_NAME'],
        source_filename=source_filename,
        target_bucket=current_app.config['INVALID_PDF_BUCKET_NAME'],
        target_filename=source_filename,
        metadata=metadata
    )


def move_uploaded_pdf_to_letters_bucket(source_filename, upload_filename):
    _move_s3_object(
        source_bucket=current_app.config['TRANSIENT_UPLOADED_LETTERS'],
        source_filename=source_filename,
        target_bucket=current_app.config['LETTERS_PDF_BUCKET_NAME'],
        target_filename=upload_filename,
    )


def move_sanitised_letter_to_test_or_live_pdf_bucket(filename, is_test_letter, created_at):
    target_bucket_config = 'TEST_LETTERS_BUCKET_NAME' if is_test_letter else 'LETTERS_PDF_BUCKET_NAME'
    target_bucket_name = current_app.config[target_bucket_config]
    target_filename = get_folder_name(created_at, dont_use_sending_date=is_test_letter) + filename

    _move_s3_object(
        source_bucket=current_app.config['LETTER_SANITISE_BUCKET_NAME'],
        source_filename=filename,
        target_bucket=target_bucket_name,
        target_filename=target_filename,
    )


def get_file_names_from_error_bucket():
    s3 = boto3.resource('s3')
    scan_bucket = current_app.config['LETTERS_SCAN_BUCKET_NAME']
    bucket = s3.Bucket(scan_bucket)

    return bucket.objects.filter(Prefix="ERROR")


def get_letter_pdf_and_metadata(notification):
    bucket_name, prefix = get_bucket_name_and_prefix_for_notification(notification)

    s3 = boto3.resource('s3')
    bucket = s3.Bucket(bucket_name)
    item = next(x for x in bucket.objects.filter(Prefix=prefix))

    obj = s3.Object(
        bucket_name=bucket_name,
        key=item.key
    ).get()
    return obj["Body"].read(), obj["Metadata"]


def _move_s3_object(source_bucket, source_filename, target_bucket, target_filename, metadata=None):
    s3 = boto3.resource('s3')
    copy_source = {'Bucket': source_bucket, 'Key': source_filename}

    target_bucket = s3.Bucket(target_bucket)
    obj = target_bucket.Object(target_filename)

    # Tags are copied across but the expiration time is reset in the destination bucket
    # e.g. if a file has 5 days left to expire on a ONE_WEEK retention in the source bucket,
    # in the destination bucket the expiration time will be reset to 7 days left to expire
    put_args = {'ServerSideEncryption': 'AES256'}
    if metadata:
        put_args['Metadata'] = metadata
        put_args["MetadataDirective"] = "REPLACE"
    obj.copy(copy_source, ExtraArgs=put_args)

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


def get_page_count(pdf):
    return pdf_page_count(io.BytesIO(pdf))


def get_billable_units_for_letter_page_count(page_count):
    if not page_count:
        return 0
    pages_per_sheet = 2
    billable_units = math.ceil(page_count / pages_per_sheet)
    return billable_units
