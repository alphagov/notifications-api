from datetime import datetime, timedelta

import boto3
from flask import current_app

from notifications_utils.s3 import s3upload

from app.variables import Retention


LETTERS_PDF_FILE_LOCATION_STRUCTURE = \
    '{folder}/NOTIFY.{reference}.{duplex}.{letter_class}.{colour}.{crown}.{date}.pdf'

PRECOMPILED_BUCKET_PREFIX = '{folder}/NOTIFY.{reference}'


def get_letter_pdf_filename(reference, crown):
    now = datetime.utcnow()

    print_datetime = now
    if now.time() > current_app.config.get('LETTER_PROCESSING_DEADLINE'):
        print_datetime = now + timedelta(days=1)

    upload_file_name = LETTERS_PDF_FILE_LOCATION_STRUCTURE.format(
        folder=print_datetime.date(),
        reference=reference,
        duplex="D",
        letter_class="2",
        colour="C",
        crown="C" if crown else "N",
        date=now.strftime('%Y%m%d%H%M%S')
    ).upper()

    return upload_file_name


def get_bucket_prefix_for_notification(notification):
    upload_file_name = PRECOMPILED_BUCKET_PREFIX.format(
        folder=notification.created_at.date(),
        reference=notification.reference
    ).upper()

    return upload_file_name


def upload_letter_pdf(notification, pdf_data):
    current_app.logger.info("PDF Letter {} reference {} created at {}, {} bytes".format(
        notification.id, notification.reference, notification.created_at, len(pdf_data)))

    upload_file_name = get_letter_pdf_filename(
        notification.reference, notification.service.crown)

    s3upload(
        filedata=pdf_data,
        region=current_app.config['AWS_REGION'],
        bucket_name=current_app.config['LETTERS_PDF_BUCKET_NAME'],
        file_location=upload_file_name,
        tags={Retention.KEY: Retention.ONE_WEEK}
    )

    current_app.logger.info("Uploaded letters PDF {} to {} for notification id {}".format(
        upload_file_name, current_app.config['LETTERS_PDF_BUCKET_NAME'], notification.id))


def get_letter_pdf(notification):
    bucket_name = current_app.config['LETTERS_PDF_BUCKET_NAME']

    s3 = boto3.resource('s3')
    bucket = s3.Bucket(bucket_name)

    for item in bucket.objects.filter(Prefix=get_bucket_prefix_for_notification(notification)):
        obj = s3.Object(
            bucket_name=bucket_name,
            key=item.key
        )
        file_content = obj.get()["Body"].read()

    return file_content
