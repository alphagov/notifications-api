import math
import base64
from datetime import datetime
from uuid import UUID
from hashlib import sha512
from base64 import urlsafe_b64encode

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
    copy_redaction_failed_pdf,
    get_billable_units_for_letter_page_count,
    get_reference_from_filename,
    get_folder_name,
    upload_letter_pdf,
    ScanErrorType,
    move_failed_pdf,
    move_scan_to_invalid_pdf_bucket,
    move_error_pdf_to_scan_bucket,
    get_file_names_from_error_bucket,
)
from app.models import (
    KEY_TYPE_TEST,
    NOTIFICATION_CREATED,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_TECHNICAL_FAILURE,
    NOTIFICATION_VALIDATION_FAILED,
    NOTIFICATION_VIRUS_SCAN_FAILED,
)
from app.cronitor import cronitor


@notify_celery.task(bind=True, name="create-letters-pdf", max_retries=15, default_retry_delay=300)
@statsd(namespace="tasks")
def create_letters_pdf(self, notification_id):
    try:
        notification = get_notification_by_id(notification_id, _raise=True)
        pdf_data, billable_units = get_letters_pdf(
            notification.template,
            contact_block=notification.reply_to_text,
            filename=notification.service.letter_branding and notification.service.letter_branding.filename,
            values=notification.personalisation
        )

        upload_letter_pdf(notification, pdf_data)

        if notification.key_type != KEY_TYPE_TEST:
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
            current_app.logger.error(
                "RETRY FAILED: task create_letters_pdf failed for notification {}".format(notification_id),
            )
            update_notification_status_by_id(notification_id, 'technical-failure')


def get_letters_pdf(template, contact_block, filename, values):
    template_for_letter_print = {
        "subject": template.subject,
        "content": template.content
    }

    data = {
        'letter_contact_block': contact_block,
        'template': template_for_letter_print,
        'values': values,
        'filename': filename,
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
@cronitor("collate-letter-pdfs-for-day")
def collate_letter_pdfs_for_day(date=None):
    if not date:
        # Using the truncated date is ok because UTC to BST does not make a difference to the date,
        # since it is triggered mid afternoon.
        date = datetime.utcnow().strftime("%Y-%m-%d")

    letter_pdfs = sorted(
        s3.get_s3_bucket_objects(
            current_app.config['LETTERS_PDF_BUCKET_NAME'],
            subfolder=date
        ),
        key=lambda letter: letter['Key']
    )
    for i, letters in enumerate(group_letters(letter_pdfs)):
        filenames = [letter['Key'] for letter in letters]

        hash = urlsafe_b64encode(sha512(''.join(filenames).encode()).digest())[:20].decode()
        # eg NOTIFY.2018-12-31.001.Wjrui5nAvObjPd-3GEL-.ZIP
        dvla_filename = 'NOTIFY.{date}.{num:03}.{hash}.ZIP'.format(
            date=date,
            num=i + 1,
            hash=hash
        )

        current_app.logger.info(
            'Calling task zip-and-send-letter-pdfs for {} pdfs to upload {} with total size {:,} bytes'.format(
                len(filenames),
                dvla_filename,
                sum(letter['Size'] for letter in letters)
            )
        )
        notify_celery.send_task(
            name=TaskNames.ZIP_AND_SEND_LETTER_PDFS,
            kwargs={
                'filenames_to_zip': filenames,
                'upload_filename': dvla_filename
            },
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

    sanitise_response, result = _sanitise_precompiled_pdf(self, notification, old_pdf)
    new_pdf = None
    if result == 'validation_passed':
        new_pdf = base64.b64decode(sanitise_response["file"].encode())

        redaction_failed_message = sanitise_response.get("redaction_failed_message")
        if redaction_failed_message and not is_test_key:
            current_app.logger.info('{} for notification id {} ({})'.format(
                redaction_failed_message, notification.id, filename)
            )
            copy_redaction_failed_pdf(filename)

    billable_units = get_billable_units_for_letter_page_count(sanitise_response.get("page_count"))

    # TODO: Remove this once CYSP update their template to not cross over the margins
    if notification.service_id == UUID('fe44178f-3b45-4625-9f85-2264a36dd9ec'):  # CYSP
        # Check your state pension submit letters with good addresses and notify tags, so just use their supplied pdf
        new_pdf = old_pdf

    if result == 'validation_failed' and not new_pdf:
        current_app.logger.info('Invalid precompiled pdf received {} ({})'.format(notification.id, filename))
        _move_invalid_letter_and_update_status(
            notification=notification,
            filename=filename,
            scan_pdf_object=scan_pdf_object,
            message=sanitise_response["message"],
            invalid_pages=sanitise_response.get("invalid_pages"),
            page_count=sanitise_response.get("page_count")
        )
        return

    current_app.logger.info('notification id {} ({}) sanitised and ready to send'.format(notification.id, filename))

    try:
        _upload_pdf_to_test_or_live_pdf_bucket(
            new_pdf,
            filename,
            is_test_letter=is_test_key,
            created_at=notification.created_at
        )

        update_letter_pdf_status(
            reference=reference,
            status=NOTIFICATION_DELIVERED if is_test_key else NOTIFICATION_CREATED,
            billable_units=billable_units
        )
        scan_pdf_object.delete()
    except BotoClientError:
        current_app.logger.exception(
            "Error uploading letter to live pdf bucket for notification: {}".format(notification.id)
        )
        update_notification_status_by_id(notification.id, NOTIFICATION_TECHNICAL_FAILURE)


def _move_invalid_letter_and_update_status(
    *, notification, filename, scan_pdf_object, message=None, invalid_pages=None, page_count=None
):
    try:
        move_scan_to_invalid_pdf_bucket(
            source_filename=filename,
            message=message,
            invalid_pages=invalid_pages,
            page_count=page_count
        )
        scan_pdf_object.delete()

        update_letter_pdf_status(
            reference=notification.reference,
            status=NOTIFICATION_VALIDATION_FAILED,
            billable_units=0)
    except BotoClientError:
        current_app.logger.exception(
            "Error when moving letter with id {} to invalid PDF bucket".format(notification.id)
        )
        update_notification_status_by_id(notification.id, NOTIFICATION_TECHNICAL_FAILURE)


def _upload_pdf_to_test_or_live_pdf_bucket(pdf_data, filename, is_test_letter, created_at):
    target_bucket_config = 'TEST_LETTERS_BUCKET_NAME' if is_test_letter else 'LETTERS_PDF_BUCKET_NAME'
    target_bucket_name = current_app.config[target_bucket_config]
    target_filename = get_folder_name(created_at, dont_use_sending_date=is_test_letter) + filename

    s3upload(
        filedata=pdf_data,
        region=current_app.config['AWS_REGION'],
        bucket_name=target_bucket_name,
        file_location=target_filename
    )


def _sanitise_precompiled_pdf(self, notification, precompiled_pdf):
    try:
        response = requests_post(
            '{}/precompiled/sanitise'.format(
                current_app.config['TEMPLATE_PREVIEW_API_HOST']
            ),
            data=precompiled_pdf,
            headers={'Authorization': 'Token {}'.format(current_app.config['TEMPLATE_PREVIEW_API_KEY']),
                     'Service-ID': str(notification.service_id),
                     'Notification-ID': str(notification.id)}
        )
        response.raise_for_status()
        return response.json(), "validation_passed"
    except RequestException as ex:
        if ex.response is not None and ex.response.status_code == 400:
            message = "sanitise_precompiled_pdf validation error for notification: {}. ".format(notification.id)
            if response.json().get("message"):
                message += response.json()["message"]
                if response.json().get("invalid_pages"):
                    message += (" on pages: " + ", ".join(map(str, response.json()["invalid_pages"])))

            current_app.logger.info(
                message
            )
            return response.json(), "validation_failed"

        try:
            current_app.logger.exception(
                "sanitise_precompiled_pdf failed for notification: {}".format(notification.id)
            )
            self.retry(queue=QueueNames.RETRY)
        except MaxRetriesExceededError:
            current_app.logger.error(
                "RETRY FAILED: sanitise_precompiled_pdf failed for notification {}".format(notification.id),
            )

            notification.status = NOTIFICATION_TECHNICAL_FAILURE
            dao_update_notification(notification)
            raise


@notify_celery.task(name='process-virus-scan-failed')
def process_virus_scan_failed(filename):
    move_failed_pdf(filename, ScanErrorType.FAILURE)
    reference = get_reference_from_filename(filename)
    notification = dao_get_notification_by_reference(reference)
    updated_count = update_letter_pdf_status(reference, NOTIFICATION_VIRUS_SCAN_FAILED, billable_units=0)

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
    updated_count = update_letter_pdf_status(reference, NOTIFICATION_TECHNICAL_FAILURE, billable_units=0)

    if updated_count != 1:
        raise Exception(
            "There should only be one letter notification for each reference. Found {} notifications".format(
                updated_count
            )
        )
    error = VirusScanError('notification id {} Virus scan error: {}'.format(notification.id, filename))
    current_app.logger.exception(error)
    raise error


def update_letter_pdf_status(reference, status, billable_units):
    return dao_update_notifications_by_reference(
        references=[reference],
        update_dict={
            'status': status,
            'billable_units': billable_units,
            'updated_at': datetime.utcnow()
        })[0]


def replay_letters_in_error(filename=None):
    # This method can be used to replay letters that end up in the ERROR directory.
    # We had an incident where clamAV was not processing the virus scan.
    if filename:
        move_error_pdf_to_scan_bucket(filename)
        # call task to add the filename to anti virus queue
        current_app.logger.info("Calling scan_file for: {}".format(filename))

        if current_app.config['ANTIVIRUS_ENABLED']:
            notify_celery.send_task(
                name=TaskNames.SCAN_FILE,
                kwargs={'filename': filename},
                queue=QueueNames.ANTIVIRUS,
            )
        else:
            # stub out antivirus in dev
            process_virus_scan_passed.apply_async(
                kwargs={'filename': filename},
                queue=QueueNames.LETTERS,
            )
    else:
        error_files = get_file_names_from_error_bucket()
        for item in error_files:
            moved_file_name = item.key.split('/')[1]
            current_app.logger.info("Calling scan_file for: {}".format(moved_file_name))
            move_error_pdf_to_scan_bucket(moved_file_name)
            # call task to add the filename to anti virus queue
            if current_app.config['ANTIVIRUS_ENABLED']:
                notify_celery.send_task(
                    name=TaskNames.SCAN_FILE,
                    kwargs={'filename': moved_file_name},
                    queue=QueueNames.ANTIVIRUS,
                )
            else:
                # stub out antivirus in dev
                process_virus_scan_passed.apply_async(
                    kwargs={'filename': moved_file_name},
                    queue=QueueNames.LETTERS,
                )
