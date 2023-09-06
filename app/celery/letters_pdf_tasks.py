from base64 import urlsafe_b64encode
from datetime import datetime, timedelta
from datetime import time as dt_time
from hashlib import sha512

from botocore.exceptions import ClientError as BotoClientError
from flask import current_app
from notifications_utils.letter_timings import LETTER_PROCESSING_DEADLINE
from notifications_utils.postal_address import PostalAddress
from notifications_utils.timezones import convert_bst_to_utc, convert_utc_to_bst

from app import encryption, notify_celery
from app.aws import s3
from app.celery.provider_tasks import deliver_letter
from app.config import QueueNames, TaskNames
from app.constants import (
    INTERNATIONAL_LETTERS,
    INTERNATIONAL_POSTAGE_TYPES,
    KEY_TYPE_NORMAL,
    KEY_TYPE_TEST,
    NOTIFICATION_CREATED,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_PENDING_VIRUS_CHECK,
    NOTIFICATION_TECHNICAL_FAILURE,
    NOTIFICATION_VALIDATION_FAILED,
    NOTIFICATION_VIRUS_SCAN_FAILED,
    POSTAGE_TYPES,
    RESOLVE_POSTAGE_FOR_FILE_NAME,
)
from app.cronitor import cronitor
from app.dao.notifications_dao import (
    dao_get_letters_and_sheets_volume_by_postage,
    dao_get_letters_to_be_printed,
    dao_get_notification_by_reference,
    dao_record_notification_event_via_celery,
    dao_update_notification,
    dao_update_notifications_by_reference,
    get_notification_by_id,
    update_notification_status_by_id,
)
from app.dao.templates_dao import dao_get_template_by_id
from app.errors import VirusScanError
from app.exceptions import NotificationTechnicalFailureException
from app.letters.utils import (
    LetterPDFNotFound,
    ScanErrorType,
    find_letter_pdf_in_s3,
    generate_letter_pdf_filename,
    get_billable_units_for_letter_page_count,
    get_file_names_from_error_bucket,
    get_folder_name,
    get_reference_from_filename,
    move_error_pdf_to_scan_bucket,
    move_failed_pdf,
    move_sanitised_letter_to_test_or_live_pdf_bucket,
    move_scan_to_invalid_pdf_bucket,
)
from app.models import Service


@notify_celery.task(bind=True, name="get-pdf-for-templated-letter", max_retries=15, default_retry_delay=300)
def get_pdf_for_templated_letter(self, notification_id):
    try:
        notification = get_notification_by_id(notification_id, _raise=True)
        letter_filename = generate_letter_pdf_filename(
            reference=notification.reference,
            created_at=notification.created_at,
            ignore_folder=notification.key_type == KEY_TYPE_TEST,
            postage=notification.postage,
        )

        letter_attachment_json = (
            notification.template.letter_attachment.serialize() if notification.template.letter_attachment_id else None
        )

        letter_data = {
            "letter_contact_block": notification.reply_to_text,
            "template": {
                "service": str(notification.service_id),
                "subject": notification.template.subject,
                "content": notification.template.content,
                "template_type": notification.template.template_type,
                "letter_attachment": letter_attachment_json,
            },
            "values": notification.personalisation,
            "logo_filename": notification.service.letter_branding and notification.service.letter_branding.filename,
            "letter_filename": letter_filename,
            "notification_id": str(notification_id),
            "key_type": notification.key_type,
        }

        encrypted_data = encryption.encrypt(letter_data)

        notify_celery.send_task(
            name=TaskNames.CREATE_PDF_FOR_TEMPLATED_LETTER, args=(encrypted_data,), queue=QueueNames.SANITISE_LETTERS
        )
    except Exception as e:
        try:
            current_app.logger.exception(
                "RETRY: calling create-letter-pdf task for notification %s failed", notification_id
            )
            self.retry(exc=e, queue=QueueNames.RETRY)
        except self.MaxRetriesExceededError as e:
            message = (
                f"RETRY FAILED: Max retries reached. "
                f"The task create-letter-pdf failed for notification id {notification_id}. "
                f"Notification has been updated to technical-failure"
            )
            update_notification_status_by_id(notification_id, NOTIFICATION_TECHNICAL_FAILURE)
            raise NotificationTechnicalFailureException(message) from e


@notify_celery.task(bind=True, name="update-billable-units-for-letter", max_retries=15, default_retry_delay=300)
def update_billable_units_for_letter(self, notification_id, page_count):
    notification = get_notification_by_id(notification_id, _raise=True)

    billable_units = get_billable_units_for_letter_page_count(page_count)

    if notification.key_type != KEY_TYPE_TEST:
        notification.billable_units = billable_units
        dao_update_notification(notification)

        current_app.logger.info(
            "Letter notification id: %(id)s reference %(ref)s: billable units set to %(units)s",
            dict(id=notification_id, ref=notification.reference, units=billable_units),
        )


@notify_celery.task(
    bind=True, name="update-validation-failed-for-templated-letter", max_retries=15, default_retry_delay=300
)
def update_validation_failed_for_templated_letter(self, notification_id, page_count):
    notification = get_notification_by_id(notification_id, _raise=True)
    notification.status = NOTIFICATION_VALIDATION_FAILED
    dao_update_notification(notification)
    dao_record_notification_event_via_celery(notification)
    current_app.logger.info(
        "Validation failed: letter is too long %(page_count)s for letter with id: %(id)s",
        dict(page_count=page_count, id=notification_id),
    )


@notify_celery.task(name="collate-letter-pdfs-to-be-sent")
@cronitor("collate-letter-pdfs-to-be-sent")
def collate_letter_pdfs_to_be_sent(print_run_deadline_utc_str: str):
    """
    Finds all letters which are still waiting to be sent to DVLA for printing

    This would usually be run at 5.50pm and collect up letters created between before 5:30pm today
    that have not yet been sent.
    """
    print_run_deadline_local = convert_utc_to_bst(datetime.fromisoformat(print_run_deadline_utc_str))
    _get_letters_and_sheets_volumes_and_send_to_dvla(print_run_deadline_local)

    for postage in POSTAGE_TYPES:
        if (
            current_app.config["DVLA_API_ENABLED"]
            and postage not in current_app.config["DVLA_API_POSTAGE_TYPE_EXCLUDE_LIST"]
        ):
            send_dvla_letters_via_api(print_run_deadline_local, postage)
        else:
            _collate_letter_pdfs_to_be_sent_for_postage(print_run_deadline_local, postage)

    current_app.logger.info("finished collate-letter-pdfs-to-be-sent")


def _collate_letter_pdfs_to_be_sent_for_postage(print_run_deadline_local, postage):
    current_app.logger.info("starting collate-letter-pdfs-to-be-sent processing for postage class %s", postage)
    letters_to_print = get_key_and_size_of_letters_to_be_sent_to_print(print_run_deadline_local, postage)

    for i, letters in enumerate(group_letters(letters_to_print)):
        filenames = [letter["Key"] for letter in letters]

        service_id = letters[0]["ServiceId"]
        organisation_id = letters[0]["OrganisationId"]

        hash = urlsafe_b64encode(sha512("".join(filenames).encode()).digest())[:20].decode()
        # eg NOTIFY.2018-12-31.001.Wjrui5nAvObjPd-3GEL-.ZIP
        dvla_filename = "NOTIFY.{date}.{postage}.{num:03}.{hash}.{service_id}.{organisation_id}.ZIP".format(
            date=print_run_deadline_local.strftime("%Y-%m-%d"),
            postage=RESOLVE_POSTAGE_FOR_FILE_NAME[postage],
            num=i + 1,
            hash=hash,
            service_id=service_id,
            organisation_id=organisation_id,
        )

        current_app.logger.info(
            (
                "Calling task zip-and-send-letter-pdfs for %(num)s pdfs to upload %(dvla_filename)s "
                "with total size %(size)s bytes"
            ),
            dict(
                num=len(filenames),
                dvla_filename=dvla_filename,
                size="{:,}".format(sum(letter["Size"] for letter in letters)),
            ),
        )
        notify_celery.send_task(
            name=TaskNames.ZIP_AND_SEND_LETTER_PDFS,
            kwargs={"filenames_to_zip": filenames, "upload_filename": dvla_filename},
            queue=QueueNames.PROCESS_FTP,
            compression="zlib",
        )
    current_app.logger.info("finished collate-letter-pdfs-to-be-sent processing for postage class %s", postage)


@notify_celery.task(name="check-time-to-collate-letters")
def check_time_to_collate_letters():
    """Check whether we need to start collating letters and sending them to DVLA for processing.

    This task is scheduled via celery-beat to run at 16:50 and 17:50 UTC every day. This task is responsible for working
    out whether it's running at 17:50 local time: if it is, then letter collation itself will be triggered and all
    letters submitted to Notify before 17:30 local time will be collated and sent over.
    """
    datetime_local = convert_utc_to_bst(datetime.utcnow())

    if not (dt_time(17, 50) <= datetime_local.time() < dt_time(18, 50)):
        current_app.logger.info("Ignoring collate_letter_pdfs_to_be_sent task outside of expected celery task window")
        return

    if datetime_local.time() < LETTER_PROCESSING_DEADLINE:
        datetime_local = datetime_local - timedelta(days=1)

    print_run_deadline_utc = convert_bst_to_utc(datetime_local.replace(hour=17, minute=30, second=0, microsecond=0))

    collate_letter_pdfs_to_be_sent.apply_async([print_run_deadline_utc.isoformat()], queue=QueueNames.PERIODIC)


def _get_letters_and_sheets_volumes_and_send_to_dvla(print_run_deadline_local):
    letters_volumes = dao_get_letters_and_sheets_volume_by_postage(print_run_deadline_local)
    send_letters_volume_email_to_dvla(letters_volumes, print_run_deadline_local.date())


def send_letters_volume_email_to_dvla(letters_volumes, date):
    personalisation = {
        "total_volume": 0,
        "first_class_volume": 0,
        "second_class_volume": 0,
        "international_volume": 0,
        "total_sheets": 0,
        "first_class_sheets": 0,
        "second_class_sheets": 0,
        "international_sheets": 0,
        "date": date.strftime("%d %B %Y"),
    }
    for item in letters_volumes:
        personalisation["total_volume"] += item.letters_count
        personalisation["total_sheets"] += item.sheets_count
        if f"{item.postage}_class_volume" in personalisation:
            personalisation[f"{item.postage}_class_volume"] = item.letters_count
            personalisation[f"{item.postage}_class_sheets"] = item.sheets_count
        else:
            personalisation["international_volume"] += item.letters_count
            personalisation["international_sheets"] += item.sheets_count

    template = dao_get_template_by_id(current_app.config["LETTERS_VOLUME_EMAIL_TEMPLATE_ID"])
    recipients = current_app.config["DVLA_EMAIL_ADDRESSES"]
    reply_to = template.service.get_default_reply_to_email_address()
    service = Service.query.get(current_app.config["NOTIFY_SERVICE_ID"])

    # avoid circular imports:
    from app.notifications.process_notifications import (
        persist_notification,
        send_notification_to_queue,
    )

    for recipient in recipients:
        saved_notification = persist_notification(
            template_id=template.id,
            template_version=template.version,
            recipient=recipient,
            service=service,
            personalisation=personalisation,
            notification_type=template.template_type,
            api_key_id=None,
            key_type=KEY_TYPE_NORMAL,
            reply_to_text=reply_to,
        )

        send_notification_to_queue(saved_notification, queue=QueueNames.NOTIFY)


def get_key_and_size_of_letters_to_be_sent_to_print(print_run_deadline_local, postage):
    letters_awaiting_sending = dao_get_letters_to_be_printed(print_run_deadline_local, postage)
    for letter in letters_awaiting_sending:
        try:
            letter_pdf = find_letter_pdf_in_s3(letter)
            yield {
                "Key": letter_pdf.key,
                "Size": letter_pdf.size,
                "ServiceId": str(letter.service_id),
                "OrganisationId": str(letter.service.organisation_id),
            }
        except (BotoClientError, LetterPDFNotFound):
            current_app.logger.exception(
                "Error getting letter from bucket for notification: %s with reference: %s", letter.id, letter.reference
            )


def group_letters(letter_pdfs):
    """
    Group letters in chunks of MAX_LETTER_PDF_ZIP_FILESIZE. Will add files to lists, never going over that size.
    If a single file is (somehow) larger than MAX_LETTER_PDF_ZIP_FILESIZE that'll be in a list on it's own.
    If there are no files, will just exit (rather than yielding an empty list).
    """
    running_filesize = 0
    list_of_files = []
    service_id = None
    for letter in letter_pdfs:
        if letter["Key"].lower().endswith(".pdf"):
            if not service_id:
                service_id = letter["ServiceId"]
            if (
                running_filesize + letter["Size"] > current_app.config["MAX_LETTER_PDF_ZIP_FILESIZE"]
                or len(list_of_files) >= current_app.config["MAX_LETTER_PDF_COUNT_PER_ZIP"]
                or letter["ServiceId"] != service_id
            ):
                yield list_of_files
                running_filesize = 0
                list_of_files = []
                service_id = None

            if not service_id:
                service_id = letter["ServiceId"]
            running_filesize += letter["Size"]
            list_of_files.append(letter)

    if list_of_files:
        yield list_of_files


def send_dvla_letters_via_api(print_run_deadline_local, postage):
    current_app.logger.info("send-dvla-letters-for-day-via-api - starting queuing for postage class %s", postage)
    for letter in dao_get_letters_to_be_printed(print_run_deadline_local, postage):
        deliver_letter.apply_async(kwargs={"notification_id": letter.id}, queue=QueueNames.SEND_LETTER)

    current_app.logger.info("send-dvla-letters-for-day-via-api - finished queuing for postage class %s", postage)


@notify_celery.task(bind=True, name="sanitise-letter", max_retries=15, default_retry_delay=300)
def sanitise_letter(self, filename):
    try:
        reference = get_reference_from_filename(filename)
        notification = dao_get_notification_by_reference(reference)

        current_app.logger.info("Notification ID %s Virus scan passed: %s", notification.id, filename)

        if notification.status != NOTIFICATION_PENDING_VIRUS_CHECK:
            current_app.logger.info(
                "Sanitise letter called for notification %s which is in %s state", notification.id, notification.status
            )
            return

        notify_celery.send_task(
            name=TaskNames.SANITISE_LETTER,
            kwargs={
                "notification_id": str(notification.id),
                "filename": filename,
                "allow_international_letters": notification.service.has_permission(INTERNATIONAL_LETTERS),
            },
            queue=QueueNames.SANITISE_LETTERS,
        )
    except Exception:
        try:
            current_app.logger.exception(
                "RETRY: calling sanitise_letter task for notification %s failed", notification.id
            )
            self.retry(queue=QueueNames.RETRY)
        except self.MaxRetriesExceededError as e:
            message = (
                "RETRY FAILED: Max retries reached. "
                "The task sanitise_letter failed for notification {}. "
                "Notification has been updated to technical-failure".format(notification.id)
            )
            update_notification_status_by_id(notification.id, NOTIFICATION_TECHNICAL_FAILURE)
            raise NotificationTechnicalFailureException(message) from e


@notify_celery.task(bind=True, name="process-sanitised-letter", max_retries=15, default_retry_delay=300)
def process_sanitised_letter(self, sanitise_data):
    letter_details = encryption.decrypt(sanitise_data)

    filename = letter_details["filename"]
    notification_id = letter_details["notification_id"]

    current_app.logger.info("Processing sanitised letter with id %s", notification_id)
    notification = get_notification_by_id(notification_id, _raise=True)

    if notification.status != NOTIFICATION_PENDING_VIRUS_CHECK:
        current_app.logger.info(
            "process-sanitised-letter task called for notification %s which is in %s state",
            notification.id,
            notification.status,
        )
        return

    try:
        original_pdf_object = s3.get_s3_object(current_app.config["S3_BUCKET_LETTERS_SCAN"], filename)

        if letter_details["validation_status"] == "failed":
            current_app.logger.info(
                "Processing invalid precompiled pdf with id %s (file %s)", notification_id, filename
            )

            _move_invalid_letter_and_update_status(
                notification=notification,
                filename=filename,
                scan_pdf_object=original_pdf_object,
                message=letter_details["message"],
                invalid_pages=letter_details["invalid_pages"],
                page_count=letter_details["page_count"],
            )
            return

        current_app.logger.info("Processing valid precompiled pdf with id %s (file %s)", notification_id, filename)

        billable_units = get_billable_units_for_letter_page_count(letter_details["page_count"])
        is_test_key = notification.key_type == KEY_TYPE_TEST

        # Updating the notification needs to happen before the file is moved. This is so that if updating the
        # notification fails, the task can retry because the file is in the same place.
        update_letter_pdf_status(
            reference=notification.reference,
            status=NOTIFICATION_DELIVERED if is_test_key else NOTIFICATION_CREATED,
            billable_units=billable_units,
            recipient_address=letter_details["address"],
        )

        # The original filename could be wrong because we didn't know the postage.
        # Now we know if the letter is international, we can check what the filename should be.
        upload_file_name = generate_letter_pdf_filename(
            reference=notification.reference,
            created_at=notification.created_at,
            ignore_folder=True,
            postage=notification.postage,
        )

        move_sanitised_letter_to_test_or_live_pdf_bucket(
            filename,
            is_test_key,
            notification.created_at,
            upload_file_name,
        )
        # We've moved the sanitised PDF from the sanitise bucket, but still need to delete the original file:
        original_pdf_object.delete()

    except BotoClientError as e:
        # Boto exceptions are likely to be caused by the file(s) being in the wrong place, so retrying won't help -
        # we'll need to manually investigate
        current_app.logger.exception(
            "Boto error when processing sanitised letter for notification %s (file %s)", notification.id, filename
        )
        update_notification_status_by_id(notification.id, NOTIFICATION_TECHNICAL_FAILURE)
        raise NotificationTechnicalFailureException from e
    except Exception:
        try:
            current_app.logger.exception(
                "RETRY: calling process_sanitised_letter task for notification %s failed", notification.id
            )
            self.retry(queue=QueueNames.RETRY)
        except self.MaxRetriesExceededError as e:
            message = (
                "RETRY FAILED: Max retries reached. "
                "The task process_sanitised_letter failed for notification {}. "
                "Notification has been updated to technical-failure".format(notification.id)
            )
            update_notification_status_by_id(notification.id, NOTIFICATION_TECHNICAL_FAILURE)
            raise NotificationTechnicalFailureException(message) from e


def _move_invalid_letter_and_update_status(
    *, notification, filename, scan_pdf_object, message=None, invalid_pages=None, page_count=None
):
    try:
        move_scan_to_invalid_pdf_bucket(
            source_filename=filename, message=message, invalid_pages=invalid_pages, page_count=page_count
        )
        scan_pdf_object.delete()

        update_letter_pdf_status(
            reference=notification.reference, status=NOTIFICATION_VALIDATION_FAILED, billable_units=0
        )
    except BotoClientError as e:
        current_app.logger.exception("Error when moving letter with id %s to invalid PDF bucket", notification.id)
        update_notification_status_by_id(notification.id, NOTIFICATION_TECHNICAL_FAILURE)
        raise NotificationTechnicalFailureException from e


@notify_celery.task(name="process-virus-scan-failed")
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

    error = VirusScanError("notification id {} Virus scan failed: {}".format(notification.id, filename))
    raise error


@notify_celery.task(name="process-virus-scan-error")
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
    current_app.logger.error("notification id %s Virus scan error: %s", notification.id, filename)
    raise VirusScanError("notification id {} Virus scan error: {}".format(notification.id, filename))


def update_letter_pdf_status(reference, status, billable_units, recipient_address=None):
    postage = None
    if recipient_address:
        # fix allow_international_letters
        postage = PostalAddress(
            raw_address=recipient_address.replace(",", "\n"), allow_international_letters=True
        ).postage
        postage = postage if postage in INTERNATIONAL_POSTAGE_TYPES else None
    update_dict = {"status": status, "billable_units": billable_units, "updated_at": datetime.utcnow()}
    if postage:
        update_dict.update({"postage": postage, "international": True})
    if recipient_address:
        update_dict["to"] = recipient_address
        update_dict["normalised_to"] = "".join(recipient_address.split()).lower()
    return dao_update_notifications_by_reference(references=[reference], update_dict=update_dict)[0]


def replay_letters_in_error(filename=None):
    # This method can be used to replay letters that end up in the ERROR directory.
    # We had an incident where clamAV was not processing the virus scan.
    if filename:
        move_error_pdf_to_scan_bucket(filename)
        # call task to add the filename to anti virus queue
        current_app.logger.info("Calling scan_file for: %s", filename)

        if current_app.config["ANTIVIRUS_ENABLED"]:
            notify_celery.send_task(
                name=TaskNames.SCAN_FILE,
                kwargs={"filename": filename},
                queue=QueueNames.ANTIVIRUS,
            )
        else:
            # stub out antivirus in dev
            sanitise_letter.apply_async([filename], queue=QueueNames.LETTERS)
    else:
        error_files = get_file_names_from_error_bucket()
        for item in error_files:
            moved_file_name = item.key.split("/")[1]
            current_app.logger.info("Calling scan_file for: %s", moved_file_name)
            move_error_pdf_to_scan_bucket(moved_file_name)
            # call task to add the filename to anti virus queue
            if current_app.config["ANTIVIRUS_ENABLED"]:
                notify_celery.send_task(
                    name=TaskNames.SCAN_FILE,
                    kwargs={"filename": moved_file_name},
                    queue=QueueNames.ANTIVIRUS,
                )
            else:
                # stub out antivirus in dev
                sanitise_letter.apply_async([filename], queue=QueueNames.LETTERS)


@notify_celery.task(name="resanitise-pdf")
def resanitise_pdf(notification_id):
    """
    `notification_id` is the notification id for a PDF letter which was either uploaded or sent using the API.

    This task calls the `recreate_pdf_for_precompiled_letter` template preview task which recreates the
    PDF for a letter which is already sanitised and in the letters-pdf bucket. The new file that is generated
    will then overwrite the existing letter in the letters-pdf bucket.
    """
    notification = get_notification_by_id(notification_id)

    # folder_name is the folder that the letter is in the letters-pdf bucket e.g. '2021-10-10/'
    folder_name = get_folder_name(notification.created_at)

    filename = generate_letter_pdf_filename(
        reference=notification.reference,
        created_at=notification.created_at,
        ignore_folder=True,
        postage=notification.postage,
    )

    notify_celery.send_task(
        name=TaskNames.RECREATE_PDF_FOR_PRECOMPILED_LETTER,
        kwargs={
            "notification_id": str(notification.id),
            "file_location": f"{folder_name}{filename}",
            "allow_international_letters": notification.service.has_permission(INTERNATIONAL_LETTERS),
        },
        queue=QueueNames.SANITISE_LETTERS,
    )
