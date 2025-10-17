import io
import json
import math
from datetime import datetime, timedelta
from enum import Enum

import boto3
from flask import current_app
from notifications_utils.clients.redis import daily_limit_cache_key
from notifications_utils.letter_timings import LETTER_PROCESSING_DEADLINE
from notifications_utils.pdf import pdf_page_count
from notifications_utils.s3 import s3upload
from notifications_utils.timezones import convert_utc_to_bst

from app import redis_store
from app.constants import (
    KEY_TYPE_TEST,
    LETTER_TYPE,
    NOTIFICATION_VALIDATION_FAILED,
    RESOLVE_POSTAGE_FOR_FILE_NAME,
    SECOND_CLASS,
)


class ScanErrorType(Enum):
    ERROR = 1
    FAILURE = 2


LETTERS_PDF_FILE_LOCATION_STRUCTURE = "{folder}NOTIFY.{reference}.{duplex}.{letter_class}.{colour}.{date}.pdf"

PRECOMPILED_BUCKET_PREFIX = "{folder}NOTIFY.{reference}"


def get_folder_name(created_at):
    print_datetime = convert_utc_to_bst(created_at)
    if print_datetime.time() > LETTER_PROCESSING_DEADLINE:
        print_datetime += timedelta(days=1)
    return f"{print_datetime.date()}/"


class LetterPDFNotFound(Exception):
    pass


def find_letter_pdf_in_s3(notification):
    bucket_name, prefix = get_bucket_name_and_prefix_for_notification(notification)

    s3 = boto3.resource("s3")
    bucket = s3.Bucket(bucket_name)
    try:
        item = next(x for x in bucket.objects.filter(Prefix=prefix))
    except StopIteration as e:
        raise LetterPDFNotFound(
            f"File not found in bucket {bucket_name} with prefix {prefix}",
        ) from e
    return item


def generate_letter_pdf_filename(reference, created_at, ignore_folder=False, postage=SECOND_CLASS):
    upload_file_name = LETTERS_PDF_FILE_LOCATION_STRUCTURE.format(
        folder="" if ignore_folder else get_folder_name(created_at),
        reference=reference,
        duplex="D",
        letter_class=RESOLVE_POSTAGE_FOR_FILE_NAME[postage],
        colour="C",
        date=created_at.strftime("%Y%m%d%H%M%S"),
    ).upper()
    return upload_file_name


def get_bucket_name_and_prefix_for_notification(notification):
    folder = ""
    if notification.status == NOTIFICATION_VALIDATION_FAILED:
        bucket_name = current_app.config["S3_BUCKET_INVALID_PDF"]
    elif notification.key_type == KEY_TYPE_TEST:
        bucket_name = current_app.config["S3_BUCKET_TEST_LETTERS"]
    else:
        bucket_name = current_app.config["S3_BUCKET_LETTERS_PDF"]
        folder = get_folder_name(notification.created_at)

    upload_file_name = PRECOMPILED_BUCKET_PREFIX.format(folder=folder, reference=notification.reference).upper()

    return bucket_name, upload_file_name


def get_reference_from_filename(filename):
    # filename looks like '2018-01-13/NOTIFY.ABCDEF1234567890.D.2.C.20180113120000.PDF'
    filename_parts = filename.split(".")
    return filename_parts[1]


def upload_letter_pdf(notification, pdf_data, precompiled=False):
    extra = {
        "notification_id": notification.id,
        "notification_reference": notification.reference,
        "notification_created_at": notification.created_at,
        "file_size": len(pdf_data),
    }
    current_app.logger.info(
        "PDF Letter notification %(notification_id)s reference %(notification_reference)s "
        "created at %(notification_created_at)s, %(file_size)s bytes",
        extra,
        extra=extra,
    )

    upload_file_name = generate_letter_pdf_filename(
        reference=notification.reference,
        created_at=notification.created_at,
        ignore_folder=precompiled or notification.key_type == KEY_TYPE_TEST,
        postage=notification.postage,
    )

    if precompiled:
        bucket_name = current_app.config["S3_BUCKET_LETTERS_SCAN"]
    elif notification.key_type == KEY_TYPE_TEST:
        bucket_name = current_app.config["S3_BUCKET_TEST_LETTERS"]
    else:
        bucket_name = current_app.config["S3_BUCKET_LETTERS_PDF"]

    s3upload(
        filedata=pdf_data,
        region=current_app.config["AWS_REGION"],
        bucket_name=bucket_name,
        file_location=upload_file_name,
    )

    extra = {
        "notification_id": notification.id,
        "s3_bucket": bucket_name,
        "s3_key": upload_file_name,
    }
    current_app.logger.info(
        "Uploaded letters PDF %(s3_key)s to %(s3_bucket)s for notification id %(notification_id)s", extra, extra=extra
    )
    return upload_file_name


def move_failed_pdf(source_filename, scan_error_type):
    scan_bucket = current_app.config["S3_BUCKET_LETTERS_SCAN"]

    target_filename = ("ERROR/" if scan_error_type == ScanErrorType.ERROR else "FAILURE/") + source_filename

    _move_s3_object(scan_bucket, source_filename, scan_bucket, target_filename)


def move_error_pdf_to_scan_bucket(source_filename):
    scan_bucket = current_app.config["S3_BUCKET_LETTERS_SCAN"]
    error_file = "ERROR/" + source_filename

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
        source_bucket=current_app.config["S3_BUCKET_LETTERS_SCAN"],
        source_filename=source_filename,
        target_bucket=current_app.config["S3_BUCKET_INVALID_PDF"],
        target_filename=source_filename,
        metadata=metadata,
    )


def move_uploaded_pdf_to_letters_bucket(source_filename, upload_filename):
    _move_s3_object(
        source_bucket=current_app.config["S3_BUCKET_TRANSIENT_UPLOADED_LETTERS"],
        source_filename=source_filename,
        target_bucket=current_app.config["S3_BUCKET_LETTERS_PDF"],
        target_filename=upload_filename,
    )


def move_sanitised_letter_to_test_or_live_pdf_bucket(filename, is_test_letter, created_at, new_filename):
    target_bucket_config = "S3_BUCKET_TEST_LETTERS" if is_test_letter else "S3_BUCKET_LETTERS_PDF"
    target_bucket_name = current_app.config[target_bucket_config]
    target_folder = "" if is_test_letter else get_folder_name(created_at)
    target_filename = target_folder + new_filename

    _move_s3_object(
        source_bucket=current_app.config["S3_BUCKET_LETTER_SANITISE"],
        source_filename=filename,
        target_bucket=target_bucket_name,
        target_filename=target_filename,
    )


def get_file_names_from_error_bucket():
    s3 = boto3.resource("s3")
    scan_bucket = current_app.config["S3_BUCKET_LETTERS_SCAN"]
    bucket = s3.Bucket(scan_bucket)

    return bucket.objects.filter(Prefix="ERROR")


def get_letter_pdf_and_metadata(notification):
    obj = find_letter_pdf_in_s3(notification).get()
    return obj["Body"].read(), obj["Metadata"]


def _move_s3_object(source_bucket, source_filename, target_bucket, target_filename, metadata=None):
    s3 = boto3.resource("s3")
    copy_source = {"Bucket": source_bucket, "Key": source_filename}

    target_bucket = s3.Bucket(target_bucket)
    obj = target_bucket.Object(target_filename)

    # Tags are copied across but the expiration time is reset in the destination bucket
    # e.g. if a file has 5 days left to expire on a ONE_WEEK retention in the source bucket,
    # in the destination bucket the expiration time will be reset to 7 days left to expire
    put_args = {"ServerSideEncryption": "AES256"}
    if metadata:
        put_args["Metadata"] = metadata
        put_args["MetadataDirective"] = "REPLACE"
    obj.copy(copy_source, ExtraArgs=put_args)

    s3.Object(source_bucket, source_filename).delete()

    extra = {
        "s3_bucket": source_bucket,
        "s3_key": source_filename,
        "s3_bucket_new": target_bucket,
        "s3_key_new": target_filename,
    }
    current_app.logger.info(
        "Moved letter PDF: %(s3_bucket)s/%(s3_key)s to %(s3_bucket_new)s/%(s3_key_new)s",
        extra,
        extra=extra,
    )


def letter_print_day(created_at):
    bst_print_datetime = convert_utc_to_bst(created_at) + timedelta(hours=6, minutes=30)
    bst_print_date = bst_print_datetime.date()

    current_bst_date = convert_utc_to_bst(datetime.utcnow()).date()

    if bst_print_date >= current_bst_date:
        return "today"
    else:
        print_date = bst_print_datetime.strftime("%d %B").lstrip("0")
        return f"on {print_date}"


def get_page_count(pdf):
    return pdf_page_count(io.BytesIO(pdf))


def get_billable_units_for_letter_page_count(page_count):
    if not page_count:
        return 0
    pages_per_sheet = 2
    billable_units = math.ceil(page_count / pages_per_sheet)
    return billable_units


def adjust_daily_service_limits_for_cancelled_letters(service_id, no_of_cancelled_letters, letters_created_at):
    """
    Updates the Redis values for the daily letters sent and total number of notifications sent
    by a service. These values should be decreased if letters are cancelled.

    Before updating the value, we check that the key exists and that we would not be changing its
    value to a negative number.

    We only want to update today's cached value, so if the letters were created yesterday we return
    early.
    """

    if not current_app.config["REDIS_ENABLED"]:
        return

    if letters_created_at.date() != datetime.today().date():
        return

    letters_cache_key = daily_limit_cache_key(service_id, notification_type=LETTER_TYPE)

    if (cached_letters_sent := redis_store.get(letters_cache_key)) is not None:
        if (int(cached_letters_sent) - no_of_cancelled_letters) >= 0:
            redis_store.decrby(letters_cache_key, no_of_cancelled_letters)
