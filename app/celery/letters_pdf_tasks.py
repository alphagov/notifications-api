from datetime import datetime, timedelta
from datetime import time as dt_time

from botocore.exceptions import ClientError as BotoClientError
from flask import current_app
from notifications_utils.letter_timings import LETTER_PROCESSING_DEADLINE
from notifications_utils.recipient_validation.postal_address import PostalAddress
from notifications_utils.timezones import convert_bst_to_utc, convert_utc_to_bst

from app import notify_celery, signing
from app.aws import s3
from app.celery.provider_tasks import deliver_letter
from app.config import QueueNames, TaskNames
from app.constants import (
    ECONOMY_CLASS,
    FIRST_CLASS,
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
    SECOND_CLASS,
)
from app.cronitor import cronitor
from app.dao.notifications_dao import (
    dao_get_letters_and_sheets_volume_by_postage,
    dao_get_letters_to_be_printed,
    dao_get_notification_by_reference,
    dao_update_notification,
    dao_update_notifications_by_reference,
    get_notification_by_id,
    update_notification_status_by_id,
)
from app.dao.templates_dao import dao_get_template_by_id
from app.errors import VirusScanError
from app.exceptions import NotificationTechnicalFailureException
from app.letters.utils import (
    ScanErrorType,
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
from app.utils import batched


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
                "letter_languages": notification.template.letter_languages,
                "subject": notification.template.subject,
                "content": notification.template.content,
                "letter_welsh_subject": notification.template.letter_welsh_subject,
                "letter_welsh_content": notification.template.letter_welsh_content,
                "template_type": notification.template.template_type,
                "letter_attachment": letter_attachment_json,
            },
            "values": notification.personalisation,
            "logo_filename": notification.service.letter_branding and notification.service.letter_branding.filename,
            "letter_filename": letter_filename,
            "notification_id": str(notification_id),
            "key_type": notification.key_type,
        }

        encoded_data = signing.encode(letter_data)

        notify_celery.send_task(
            name=TaskNames.CREATE_PDF_FOR_TEMPLATED_LETTER, args=(encoded_data,), queue=QueueNames.SANITISE_LETTERS
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
            {"id": notification_id, "ref": notification.reference, "units": billable_units},
        )


@notify_celery.task(
    bind=True, name="update-validation-failed-for-templated-letter", max_retries=15, default_retry_delay=300
)
def update_validation_failed_for_templated_letter(self, notification_id, page_count):
    notification = get_notification_by_id(notification_id, _raise=True)
    notification.status = NOTIFICATION_VALIDATION_FAILED
    dao_update_notification(notification)
    current_app.logger.info(
        "Validation failed: letter is too long %(page_count)s for letter with id: %(id)s",
        {"page_count": page_count, "id": notification_id},
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

    send_dvla_letters_via_api(print_run_deadline_local)

    current_app.logger.info("finished collate-letter-pdfs-to-be-sent")


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
        "economy_mail_volume": 0,
        "international_volume": 0,
        "total_sheets": 0,
        "first_class_sheets": 0,
        "second_class_sheets": 0,
        "economy_mail_sheets": 0,
        "international_sheets": 0,
        "date": date.strftime("%d %B %Y"),
    }
    for item in letters_volumes:
        personalisation["total_volume"] += item.letters_count
        personalisation["total_sheets"] += item.sheets_count
        if item.postage in (FIRST_CLASS, SECOND_CLASS):
            personalisation[f"{item.postage}_class_volume"] = item.letters_count
            personalisation[f"{item.postage}_class_sheets"] = item.sheets_count
        elif item.postage == ECONOMY_CLASS:
            personalisation["economy_mail_volume"] = item.letters_count
            personalisation["economy_mail_sheets"] = item.sheets_count
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


def send_dvla_letters_via_api(print_run_deadline_local, batch_size=100):
    current_app.logger.info("send-dvla-letters-for-day-via-api - starting queuing")
    for batch in batched(
        (row.id for row in dao_get_letters_to_be_printed(print_run_deadline_local)),
        batch_size,
    ):
        shatter_deliver_letter_tasks.apply_async([batch], queue=QueueNames.PERIODIC)


@notify_celery.task(name="shatter-deliver-letters-tasks")
def shatter_deliver_letter_tasks(notification_ids):
    # If the number or size of arguments to this function change, then the default
    # `batch_size` argument of `send_dvla_letters_via_api` needs updating to keep
    # within SQS’s maximum message size
    for id in notification_ids:
        deliver_letter.apply_async(kwargs={"notification_id": id}, queue=QueueNames.SEND_LETTER)


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
                f"The task sanitise_letter failed for notification {notification.id}. "
                "Notification has been updated to technical-failure"
            )
            update_notification_status_by_id(notification.id, NOTIFICATION_TECHNICAL_FAILURE)
            raise NotificationTechnicalFailureException(message) from e


@notify_celery.task(bind=True, name="process-sanitised-letter", max_retries=15, default_retry_delay=300)
def process_sanitised_letter(self, sanitise_data):
    letter_details = signing.decode(sanitise_data)

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

            # Log letters that fail with no fixed abode error so we can check for false positives
            if letter_details["message"] == "no-fixed-abode-address":
                current_app.logger.info(
                    "Precomiled PDF with id %s was invalid due to no fixed abode address", notification_id
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
                f"The task process_sanitised_letter failed for notification {notification.id}. "
                "Notification has been updated to technical-failure"
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
            f"There should only be one letter notification for each reference. Found {updated_count} notifications"
        )

    error = VirusScanError(f"notification id {notification.id} Virus scan failed: {filename}")
    raise error


@notify_celery.task(name="process-virus-scan-error")
def process_virus_scan_error(filename):
    move_failed_pdf(filename, ScanErrorType.ERROR)
    reference = get_reference_from_filename(filename)
    notification = dao_get_notification_by_reference(reference)
    updated_count = update_letter_pdf_status(reference, NOTIFICATION_TECHNICAL_FAILURE, billable_units=0)

    if updated_count != 1:
        raise Exception(
            f"There should only be one letter notification for each reference. Found {updated_count} notifications"
        )
    current_app.logger.error("notification id %s Virus scan error: %s", notification.id, filename)
    raise VirusScanError(f"notification id {notification.id} Virus scan error: {filename}")


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


@notify_celery.task(name="resanitise-letter-attachment")
def resanitise_letter_attachment(service_id, attachment_id, original_filename):
    """
    `service_id` is the service id for a PDF letter attachment/template.
    `attachment_id` is the attachment id for a PDF letter attachment which was uploaded for a template.
    `original_filename` is the attachment name for a PDF letter attachment.

    This task calls the `recreate-pdf-for-template-letter-attachments` template preview task which recreates the
    PDF for a letter attachment which is already sanitised and in the letters-attachment bucket. The new file
    that is generated will then overwrite the existing letter in the letter-attachments bucket.
    """

    notify_celery.send_task(
        name=TaskNames.RECREATE_PDF_FOR_TEMPLATE_LETTER_ATTACHMENTS,
        kwargs={
            "service_id": service_id,
            "attachment_id": attachment_id,
            "original_filename": original_filename,
        },
        queue=QueueNames.SANITISE_LETTERS,
    )
