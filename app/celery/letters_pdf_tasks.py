import math
from datetime import datetime

from botocore.exceptions import ClientError as BotoClientError
from flask import current_app
from requests import (
    post as requests_post,
    RequestException
)
from celery.exceptions import MaxRetriesExceededError
from notifications_utils.statsd_decorators import statsd
from notifications_utils.s3 import s3upload

from app import notify_celery
from app.aws import s3
from app.config import QueueNames, TaskNames
from app.dao.notifications_dao import (
    get_notification_by_id,
    update_notification_status_by_id,
    dao_update_notification,
    dao_get_notification_by_reference,
    dao_get_notifications_by_references,
    dao_update_notifications_by_reference,
)
from app.errors import VirusScanError
from app.letters.utils import (
    get_reference_from_filename,
    get_folder_name,
    upload_letter_pdf,
    move_failed_pdf,
    ScanErrorType,
    move_error_pdf_to_scan_bucket,
    get_file_names_from_error_bucket
)
from app.models import (
    KEY_TYPE_TEST,
    NOTIFICATION_CREATED,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_VIRUS_SCAN_FAILED,
    NOTIFICATION_TECHNICAL_FAILURE,
    # NOTIFICATION_VALIDATION_FAILED
)


@notify_celery.task(bind=True, name="create-letters-pdf", max_retries=15, default_retry_delay=300)
@statsd(namespace="tasks")
def create_letters_pdf(self, notification_id):
    try:
        notification = get_notification_by_id(notification_id, _raise=True)

        pdf_data, billable_units = get_letters_pdf(
            notification.template,
            contact_block=notification.reply_to_text,
            org_id=notification.service.dvla_organisation.id,
            values=notification.personalisation
        )

        upload_letter_pdf(notification, pdf_data)

        notification.billable_units = billable_units
        dao_update_notification(notification)

        current_app.logger.info(
            'Letter notification reference {reference}: billable units set to {billable_units}'.format(
                reference=str(notification.reference), billable_units=billable_units))

    except (RequestException, BotoClientError):
        try:
            current_app.logger.exception(
                "Letters PDF notification creation for id: {} failed".format(notification_id)
            )
            self.retry(queue=QueueNames.RETRY)
        except MaxRetriesExceededError:
            current_app.logger.exception(
                "RETRY FAILED: task create_letters_pdf failed for notification {}".format(notification_id),
            )
            update_notification_status_by_id(notification_id, 'technical-failure')


def get_letters_pdf(template, contact_block, org_id, values):
    template_for_letter_print = {
        "subject": template.subject,
        "content": template.content
    }

    data = {
        'letter_contact_block': contact_block,
        'template': template_for_letter_print,
        'values': values,
        'dvla_org_id': org_id,
    }
    resp = requests_post(
        '{}/print.pdf'.format(
            current_app.config['TEMPLATE_PREVIEW_API_HOST']
        ),
        json=data,
        headers={'Authorization': 'Token {}'.format(current_app.config['TEMPLATE_PREVIEW_API_KEY'])}
    )
    resp.raise_for_status()

    pages_per_sheet = 2
    billable_units = math.ceil(int(resp.headers.get("X-pdf-page-count", 0)) / pages_per_sheet)

    return resp.content, billable_units


@notify_celery.task(name='collate-letter-pdfs-for-day')
def collate_letter_pdfs_for_day(date):
    letter_pdfs = s3.get_s3_bucket_objects(
        current_app.config['LETTERS_PDF_BUCKET_NAME'],
        subfolder=date
    )
    for letters in group_letters(letter_pdfs):
        filenames = [letter['Key'] for letter in letters]
        current_app.logger.info(
            'Calling task zip-and-send-letter-pdfs for {} pdfs of total size {:,} bytes'.format(
                len(filenames),
                sum(letter['Size'] for letter in letters)
            )
        )
        notify_celery.send_task(
            name=TaskNames.ZIP_AND_SEND_LETTER_PDFS,
            kwargs={'filenames_to_zip': filenames},
            queue=QueueNames.PROCESS_FTP,
            compression='zlib'
        )


def group_letters(letter_pdfs):
    """
    Group letters in chunks of MAX_LETTER_PDF_ZIP_FILESIZE. Will add files to lists, never going over that size.
    If a single file is (somehow) larger than MAX_LETTER_PDF_ZIP_FILESIZE that'll be in a list on it's own.
    If there are no files, will just exit (rather than yielding an empty list).
    """
    running_filesize = 0
    list_of_files = []
    for letter in letter_pdfs:
        if letter['Key'].lower().endswith('.pdf') and letter_in_created_state(letter['Key']):
            if (
                running_filesize + letter['Size'] > current_app.config['MAX_LETTER_PDF_ZIP_FILESIZE'] or
                len(list_of_files) >= current_app.config['MAX_LETTER_PDF_COUNT_PER_ZIP']
            ):
                yield list_of_files
                running_filesize = 0
                list_of_files = []

            running_filesize += letter['Size']
            list_of_files.append(letter)

    if list_of_files:
        yield list_of_files


def letter_in_created_state(filename):
    # filename looks like '2018-01-13/NOTIFY.ABCDEF1234567890.D.2.C.C.20180113120000.PDF'
    subfolder = filename.split('/')[0]
    ref = get_reference_from_filename(filename)
    notifications = dao_get_notifications_by_references([ref])
    if notifications:
        if notifications[0].status == NOTIFICATION_CREATED:
            return True
        current_app.logger.info('Collating letters for {} but notification with reference {} already in {}'.format(
            subfolder,
            ref,
            notifications[0].status
        ))
    return False


@notify_celery.task(bind=True, name='process-virus-scan-passed', max_retries=15, default_retry_delay=300)
def process_virus_scan_passed(self, filename):
    reference = get_reference_from_filename(filename)
    notification = dao_get_notification_by_reference(reference)
    current_app.logger.info('notification id {} Virus scan passed: {}'.format(notification.id, filename))

    is_test_key = notification.key_type == KEY_TYPE_TEST

    scan_pdf_object = s3.get_s3_object(current_app.config['LETTERS_SCAN_BUCKET_NAME'], filename)
    old_pdf = scan_pdf_object.get()['Body'].read()

    new_pdf = _sanitise_precomiled_pdf(self, notification, old_pdf)

    if not new_pdf:
        current_app.logger.info('Invalid precompiled pdf received {} ({})'.format(notification.id, filename))
        # update_notification_status_by_id(notification.id, NOTIFICATION_VALIDATION_FAILED)
        # move_scan_to_invalid_pdf_bucket()  # TODO: implement this (and create bucket etc)
        # scan_pdf_object.delete()
        # return

    current_app.logger.info('notification id {} ({}) sanitised and ready to send'.format(notification.id, filename))

    # temporarily upload original pdf while testing sanitise flow.
    _upload_pdf_to_test_or_live_pdf_bucket(
        old_pdf,  # TODO: change to new_pdf
        filename,
        is_test_letter=is_test_key)

    update_letter_pdf_status(
        reference,
        NOTIFICATION_DELIVERED if is_test_key else NOTIFICATION_CREATED
    )

    scan_pdf_object.delete()


def _upload_pdf_to_test_or_live_pdf_bucket(pdf_data, filename, is_test_letter):
    target_bucket_config = 'TEST_LETTERS_BUCKET_NAME' if is_test_letter else 'LETTERS_PDF_BUCKET_NAME'
    target_bucket_name = current_app.config[target_bucket_config]
    target_filename = get_folder_name(datetime.utcnow(), is_test_letter) + filename

    s3upload(
        filedata=pdf_data,
        region=current_app.config['AWS_REGION'],
        bucket_name=target_bucket_name,
        file_location=target_filename
    )


def _sanitise_precomiled_pdf(self, notification, precompiled_pdf):
    try:
        resp = requests_post(
            '{}/precompiled/sanitise'.format(
                current_app.config['TEMPLATE_PREVIEW_API_HOST']
            ),
            data=precompiled_pdf,
            headers={'Authorization': 'Token {}'.format(current_app.config['TEMPLATE_PREVIEW_API_KEY'])}
        )
        resp.raise_for_status()
        return resp.content
    except RequestException as ex:
        if ex.response is not None and ex.response.status_code == 400:
            # validation error
            return None

        try:
            current_app.logger.exception(
                "sanitise_precomiled_pdf failed for notification: {}".format(notification.id)
            )
            self.retry(queue=QueueNames.RETRY)
        except MaxRetriesExceededError:
            current_app.logger.exception(
                "RETRY FAILED: sanitise_precomiled_pdf failed for notification {}".format(notification.id),
            )
            update_notification_status_by_id(notification.id, NOTIFICATION_TECHNICAL_FAILURE)
            raise


@notify_celery.task(name='process-virus-scan-failed')
def process_virus_scan_failed(filename):
    move_failed_pdf(filename, ScanErrorType.FAILURE)
    reference = get_reference_from_filename(filename)
    notification = dao_get_notification_by_reference(reference)
    updated_count = update_letter_pdf_status(reference, NOTIFICATION_VIRUS_SCAN_FAILED)

    if updated_count != 1:
        raise Exception(
            "There should only be one letter notification for each reference. Found {} notifications".format(
                updated_count
            )
        )

    error = VirusScanError('notification id {} Virus scan failed: {}'.format(notification.id, filename))
    current_app.logger.exception(error)
    raise error


@notify_celery.task(name='process-virus-scan-error')
def process_virus_scan_error(filename):
    move_failed_pdf(filename, ScanErrorType.ERROR)
    reference = get_reference_from_filename(filename)
    notification = dao_get_notification_by_reference(reference)
    updated_count = update_letter_pdf_status(reference, NOTIFICATION_TECHNICAL_FAILURE)

    if updated_count != 1:
        raise Exception(
            "There should only be one letter notification for each reference. Found {} notifications".format(
                updated_count
            )
        )
    error = VirusScanError('notification id {} Virus scan error: {}'.format(notification.id, filename))
    current_app.logger.exception(error)
    raise error


def update_letter_pdf_status(reference, status):
    return dao_update_notifications_by_reference(
        references=[reference],
        update_dict={
            'status': status,
            'updated_at': datetime.utcnow()
        })[0]


def replay_letters_in_error(filename=None):
    # This method can be used to replay letters that end up in the ERROR directory.
    # We had an incident where clamAV was not processing the virus scan.
    if filename:
        move_error_pdf_to_scan_bucket(filename)
        # call task to add the filename to anti virus queue
        current_app.logger.info("Calling scan_file for: {}".format(filename))
        notify_celery.send_task(
            name=TaskNames.SCAN_FILE,
            kwargs={'filename': filename},
            queue=QueueNames.ANTIVIRUS,
        )
    else:
        error_files = get_file_names_from_error_bucket()
        for item in error_files:
            moved_file_name = item.key.split('/')[1]
            current_app.logger.info("Calling scan_file for: {}".format(moved_file_name))
            move_error_pdf_to_scan_bucket(moved_file_name)
            # call task to add the filename to anti virus queue
            notify_celery.send_task(
                name=TaskNames.SCAN_FILE,
                kwargs={'filename': moved_file_name},
                queue=QueueNames.ANTIVIRUS,
            )
