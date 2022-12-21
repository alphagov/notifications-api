import json
from collections import defaultdict, namedtuple
from datetime import datetime

from flask import current_app
from notifications_utils.insensitive_dict import InsensitiveDict
from notifications_utils.postal_address import PostalAddress
from notifications_utils.recipients import RecipientCSV
from notifications_utils.timezones import convert_utc_to_bst
from requests import HTTPError, RequestException, request
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import create_random_identifier, create_uuid, encryption, notify_celery
from app.aws import s3
from app.celery import letters_pdf_tasks, provider_tasks, research_mode_tasks
from app.config import QueueNames
from app.dao.daily_sorted_letter_dao import (
    dao_create_or_update_daily_sorted_letter,
)
from app.dao.inbound_sms_dao import dao_get_inbound_sms_by_id
from app.dao.jobs_dao import dao_get_job_by_id, dao_update_job
from app.dao.notifications_dao import (
    dao_get_last_notification_added_for_job_id,
    dao_get_notification_or_history_by_reference,
    dao_update_notifications_by_reference,
    get_notification_by_id,
    update_notification_status_by_reference,
)
from app.dao.provider_details_dao import (
    get_provider_details_by_notification_type,
)
from app.dao.returned_letters_dao import insert_or_update_returned_letters
from app.dao.service_email_reply_to_dao import dao_get_reply_to_by_id
from app.dao.service_inbound_api_dao import get_service_inbound_api_for_service
from app.dao.service_sms_sender_dao import dao_get_service_sms_senders_by_id
from app.dao.templates_dao import dao_get_template_by_id
from app.exceptions import DVLAException, NotificationTechnicalFailureException
from app.models import (
    DVLA_RESPONSE_STATUS_SENT,
    EMAIL_TYPE,
    JOB_STATUS_CANCELLED,
    JOB_STATUS_FINISHED,
    JOB_STATUS_IN_PROGRESS,
    JOB_STATUS_PENDING,
    KEY_TYPE_NORMAL,
    LETTER_TYPE,
    NOTIFICATION_CREATED,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_RETURNED_LETTER,
    NOTIFICATION_SENDING,
    NOTIFICATION_TECHNICAL_FAILURE,
    NOTIFICATION_TEMPORARY_FAILURE,
    SMS_TYPE,
    DailySortedLetter,
    Service,
)
from app.notifications.process_notifications import persist_notification
from app.notifications.validators import check_service_over_daily_message_limit
from app.serialised_models import SerialisedService, SerialisedTemplate
from app.service.utils import service_allowed_to_send_to
from app.utils import DATETIME_FORMAT
from app.v2.errors import TooManyRequestsError


@notify_celery.task(name="process-job")
def process_job(job_id, sender_id=None):
    start = datetime.utcnow()
    job = dao_get_job_by_id(job_id)
    current_app.logger.info("Starting process-job task for job id {} with status: {}".format(job_id, job.job_status))

    if job.job_status != JOB_STATUS_PENDING:
        return

    service = job.service

    job.job_status = JOB_STATUS_IN_PROGRESS
    job.processing_started = start
    dao_update_job(job)

    if not service.active:
        job.job_status = JOB_STATUS_CANCELLED
        dao_update_job(job)
        current_app.logger.warning("Job {} has been cancelled, service {} is inactive".format(job_id, service.id))
        return

    if __sending_limits_for_job_exceeded(service, job, job_id):
        return

    recipient_csv, template, sender_id = get_recipient_csv_and_template_and_sender_id(job)

    current_app.logger.info("Starting job {} processing {} notifications".format(job_id, job.notification_count))

    for row in recipient_csv.get_rows():
        process_row(row, template, job, service, sender_id=sender_id)

    job_complete(job, start=start)


def job_complete(job, resumed=False, start=None):
    job.job_status = JOB_STATUS_FINISHED

    finished = datetime.utcnow()
    job.processing_finished = finished
    dao_update_job(job)

    if resumed:
        current_app.logger.info("Resumed Job {} completed at {}".format(job.id, job.created_at))
    else:
        current_app.logger.info(
            "Job {} created at {} started at {} finished at {}".format(job.id, job.created_at, start, finished)
        )


def get_recipient_csv_and_template_and_sender_id(job):
    db_template = dao_get_template_by_id(job.template_id, job.template_version)
    template = db_template._as_utils_template()

    contents, meta_data = s3.get_job_and_metadata_from_s3(service_id=str(job.service_id), job_id=str(job.id))
    recipient_csv = RecipientCSV(contents, template=template)

    return recipient_csv, template, meta_data.get("sender_id")


def process_row(row, template, job, service, sender_id=None):
    template_type = template.template_type
    encrypted = encryption.encrypt(
        {
            "template": str(template.id),
            "template_version": job.template_version,
            "job": str(job.id),
            "to": row.recipient,
            "row_number": row.index,
            "personalisation": dict(row.personalisation),
            # row.recipient_and_personalisation gets all columns for the row, even those not in template placeholders
            "client_reference": dict(row.recipient_and_personalisation).get("reference", None),
        }
    )

    send_fns = {SMS_TYPE: save_sms, EMAIL_TYPE: save_email, LETTER_TYPE: save_letter}

    send_fn = send_fns[template_type]

    task_kwargs = {}
    if sender_id:
        task_kwargs["sender_id"] = sender_id

    notification_id = create_uuid()
    send_fn.apply_async(
        (
            str(service.id),
            notification_id,
            encrypted,
        ),
        task_kwargs,
        queue=QueueNames.DATABASE if not service.research_mode else QueueNames.RESEARCH_MODE,
    )
    return notification_id


def __sending_limits_for_job_exceeded(service, job, job_id):
    notification_type = None

    rate_limits = Service.rate_limits_from_service(service)
    limit_name = rate_limits[notification_type].name
    limit_value = rate_limits[notification_type].value

    try:
        total_sent = check_service_over_daily_message_limit(
            service, KEY_TYPE_NORMAL, notification_type=notification_type
        )
        if total_sent + job.notification_count > limit_value:
            raise TooManyRequestsError(limit_name, limit_value)
        else:
            return False
    except TooManyRequestsError:
        job.job_status = "sending limits exceeded"
        job.processing_finished = datetime.utcnow()
        dao_update_job(job)
        current_app.logger.info(
            "Job {} size {} error. Sending limits ({}: {}) exceeded".format(
                job_id, job.notification_count, limit_name, limit_value
            )
        )
        return True


@notify_celery.task(bind=True, name="save-sms", max_retries=5, default_retry_delay=300)
def save_sms(self, service_id, notification_id, encrypted_notification, sender_id=None):
    notification = encryption.decrypt(encrypted_notification)
    service = SerialisedService.from_id(service_id)
    template = SerialisedTemplate.from_id_and_service_id(
        notification["template"],
        service_id=service.id,
        version=notification["template_version"],
    )

    if sender_id:
        reply_to_text = dao_get_service_sms_senders_by_id(service_id, sender_id).sms_sender
    else:
        reply_to_text = template.reply_to_text

    if not service_allowed_to_send_to(notification["to"], service, KEY_TYPE_NORMAL):
        current_app.logger.debug("SMS {} failed as restricted service".format(notification_id))
        return

    try:
        saved_notification = persist_notification(
            template_id=notification["template"],
            template_version=notification["template_version"],
            recipient=notification["to"],
            service=service,
            personalisation=notification.get("personalisation"),
            notification_type=SMS_TYPE,
            api_key_id=None,
            key_type=KEY_TYPE_NORMAL,
            created_at=datetime.utcnow(),
            job_id=notification.get("job", None),
            job_row_number=notification.get("row_number", None),
            notification_id=notification_id,
            reply_to_text=reply_to_text,
            client_reference=notification.get("client_reference", None),
        )

        provider_tasks.deliver_sms.apply_async(
            [str(saved_notification.id)],
            queue=QueueNames.SEND_SMS if not service.research_mode else QueueNames.RESEARCH_MODE,
        )

        current_app.logger.debug(
            "SMS {} created at {} for job {}".format(
                saved_notification.id, saved_notification.created_at, notification.get("job", None)
            )
        )

    except SQLAlchemyError as e:
        handle_exception(self, notification, notification_id, e)


@notify_celery.task(bind=True, name="save-email", max_retries=5, default_retry_delay=300)
def save_email(self, service_id, notification_id, encrypted_notification, sender_id=None):
    notification = encryption.decrypt(encrypted_notification)

    service = SerialisedService.from_id(service_id)
    template = SerialisedTemplate.from_id_and_service_id(
        notification["template"],
        service_id=service.id,
        version=notification["template_version"],
    )

    if sender_id:
        reply_to_text = dao_get_reply_to_by_id(service_id, sender_id).email_address
    else:
        reply_to_text = template.reply_to_text

    if not service_allowed_to_send_to(notification["to"], service, KEY_TYPE_NORMAL):
        current_app.logger.info("Email {} failed as restricted service".format(notification_id))
        return

    try:
        saved_notification = persist_notification(
            template_id=notification["template"],
            template_version=notification["template_version"],
            recipient=notification["to"],
            service=service,
            personalisation=notification.get("personalisation"),
            notification_type=EMAIL_TYPE,
            api_key_id=None,
            key_type=KEY_TYPE_NORMAL,
            created_at=datetime.utcnow(),
            job_id=notification.get("job", None),
            job_row_number=notification.get("row_number", None),
            notification_id=notification_id,
            reply_to_text=reply_to_text,
            client_reference=notification.get("client_reference", None),
        )

        provider_tasks.deliver_email.apply_async(
            [str(saved_notification.id)],
            queue=QueueNames.SEND_EMAIL if not service.research_mode else QueueNames.RESEARCH_MODE,
        )

        current_app.logger.debug("Email {} created at {}".format(saved_notification.id, saved_notification.created_at))
    except SQLAlchemyError as e:
        handle_exception(self, notification, notification_id, e)


@notify_celery.task(bind=True, name="save-api-email", max_retries=5, default_retry_delay=300)
def save_api_email(self, encrypted_notification):

    save_api_email_or_sms(self, encrypted_notification)


@notify_celery.task(bind=True, name="save-api-sms", max_retries=5, default_retry_delay=300)
def save_api_sms(self, encrypted_notification):
    save_api_email_or_sms(self, encrypted_notification)


def save_api_email_or_sms(self, encrypted_notification):
    notification = encryption.decrypt(encrypted_notification)
    service = SerialisedService.from_id(notification["service_id"])
    q = QueueNames.SEND_EMAIL if notification["notification_type"] == EMAIL_TYPE else QueueNames.SEND_SMS
    provider_task = (
        provider_tasks.deliver_email if notification["notification_type"] == EMAIL_TYPE else provider_tasks.deliver_sms
    )
    try:

        persist_notification(
            notification_id=notification["id"],
            template_id=notification["template_id"],
            template_version=notification["template_version"],
            recipient=notification["to"],
            service=service,
            personalisation=notification.get("personalisation"),
            notification_type=notification["notification_type"],
            client_reference=notification["client_reference"],
            api_key_id=notification.get("api_key_id"),
            key_type=KEY_TYPE_NORMAL,
            created_at=notification["created_at"],
            reply_to_text=notification["reply_to_text"],
            status=notification["status"],
            document_download_count=notification["document_download_count"],
        )

        q = q if not service.research_mode else QueueNames.RESEARCH_MODE
        provider_task.apply_async([notification["id"]], queue=q)
        current_app.logger.debug(
            f"{notification['notification_type']} {notification['id']} has been persisted and sent to delivery queue."
        )
    except IntegrityError:
        current_app.logger.info(f"{notification['notification_type']} {notification['id']} already exists.")

    except SQLAlchemyError:

        try:
            self.retry(queue=QueueNames.RETRY)
        except self.MaxRetriesExceededError:
            current_app.logger.error(f"Max retry failed Failed to persist notification {notification['id']}")


@notify_celery.task(bind=True, name="save-letter", max_retries=5, default_retry_delay=300)
def save_letter(
    self,
    service_id,
    notification_id,
    encrypted_notification,
):
    notification = encryption.decrypt(encrypted_notification)

    postal_address = PostalAddress.from_personalisation(InsensitiveDict(notification["personalisation"]))

    service = SerialisedService.from_id(service_id)
    template = SerialisedTemplate.from_id_and_service_id(
        notification["template"],
        service_id=service.id,
        version=notification["template_version"],
    )

    try:
        # if we don't want to actually send the letter, then start it off in SENDING so we don't pick it up
        status = NOTIFICATION_CREATED if not service.research_mode else NOTIFICATION_SENDING

        saved_notification = persist_notification(
            template_id=notification["template"],
            template_version=notification["template_version"],
            postage=postal_address.postage if postal_address.international else template.postage,
            recipient=postal_address.normalised,
            service=service,
            personalisation=notification["personalisation"],
            notification_type=LETTER_TYPE,
            api_key_id=None,
            key_type=KEY_TYPE_NORMAL,
            created_at=datetime.utcnow(),
            job_id=notification["job"],
            job_row_number=notification["row_number"],
            notification_id=notification_id,
            reference=create_random_identifier(),
            client_reference=notification.get("client_reference", None),
            reply_to_text=template.reply_to_text,
            status=status,
        )

        if not service.research_mode:
            letters_pdf_tasks.get_pdf_for_templated_letter.apply_async(
                [str(saved_notification.id)], queue=QueueNames.CREATE_LETTERS_PDF
            )
        elif current_app.config["NOTIFY_ENVIRONMENT"] in ["preview", "development"]:
            research_mode_tasks.create_fake_letter_response_file.apply_async(
                (saved_notification.reference,), queue=QueueNames.RESEARCH_MODE
            )
        else:
            update_notification_status_by_reference(saved_notification.reference, "delivered")

        current_app.logger.debug("Letter {} created at {}".format(saved_notification.id, saved_notification.created_at))
    except SQLAlchemyError as e:
        handle_exception(self, notification, notification_id, e)


@notify_celery.task(bind=True, name="update-letter-notifications-to-sent")
def update_letter_notifications_to_sent_to_dvla(self, notification_references):
    # This task will be called by the FTP app to update notifications as sent to DVLA
    provider = get_provider_details_by_notification_type(LETTER_TYPE)[0]

    updated_count, _ = dao_update_notifications_by_reference(
        notification_references,
        {
            "status": NOTIFICATION_SENDING,
            "sent_by": provider.identifier,
            "sent_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        },
    )

    current_app.logger.info("Updated {} letter notifications to sending".format(updated_count))


@notify_celery.task(bind=True, name="update-letter-notifications-to-error")
def update_letter_notifications_to_error(self, notification_references):
    # This task will be called by the FTP app to update notifications as sent to DVLA

    updated_count, _ = dao_update_notifications_by_reference(
        notification_references, {"status": NOTIFICATION_TECHNICAL_FAILURE, "updated_at": datetime.utcnow()}
    )
    message = "Updated {} letter notifications to technical-failure with references {}".format(
        updated_count, notification_references
    )
    raise NotificationTechnicalFailureException(message)


def handle_exception(task, notification, notification_id, exc):
    if not get_notification_by_id(notification_id):
        retry_msg = "{task} notification for job {job} row number {row} and notification id {noti}".format(
            task=task.__name__,
            job=notification.get("job", None),
            row=notification.get("row_number", None),
            noti=notification_id,
        )
        # Sometimes, SQS plays the same message twice. We should be able to catch an IntegrityError, but it seems
        # SQLAlchemy is throwing a FlushError. So we check if the notification id already exists then do not
        # send to the retry queue.
        current_app.logger.exception("Retry" + retry_msg)
        try:
            task.retry(queue=QueueNames.RETRY, exc=exc)
        except task.MaxRetriesExceededError:
            current_app.logger.error("Max retry failed" + retry_msg)


@notify_celery.task(bind=True, name="update-letter-notifications-statuses")
def update_letter_notifications_statuses(self, filename):
    notification_updates = parse_dvla_file(filename)

    temporary_failures = []

    for update in notification_updates:
        check_billable_units(update)
        update_letter_notification(filename, temporary_failures, update)
    if temporary_failures:
        # This will alert Notify that DVLA was unable to deliver the letters, we need to investigate
        message = "DVLA response file: {filename} has failed letters with notification.reference {failures}".format(
            filename=filename, failures=temporary_failures
        )
        raise DVLAException(message)


@notify_celery.task(bind=True, name="record-daily-sorted-counts")
def record_daily_sorted_counts(self, filename):
    sorted_letter_counts = defaultdict(int)
    notification_updates = parse_dvla_file(filename)
    for update in notification_updates:
        sorted_letter_counts[update.cost_threshold.lower()] += 1

    unknown_status = sorted_letter_counts.keys() - {"unsorted", "sorted"}
    if unknown_status:
        message = "DVLA response file: {} contains unknown Sorted status {}".format(filename, unknown_status.__repr__())
        raise DVLAException(message)

    billing_date = get_billing_date_in_bst_from_filename(filename)
    persist_daily_sorted_letter_counts(day=billing_date, file_name=filename, sorted_letter_counts=sorted_letter_counts)


def parse_dvla_file(filename):
    bucket_location = "{}-ftp".format(current_app.config["NOTIFY_EMAIL_DOMAIN"])
    response_file_content = s3.get_s3_file(bucket_location, filename)

    try:
        return process_updates_from_file(response_file_content)
    except TypeError:
        raise DVLAException("DVLA response file: {} has an invalid format".format(filename))


def get_billing_date_in_bst_from_filename(filename):
    # exclude seconds from the date since we don't need it. We got a date ending in 60 second - which is not valid.
    datetime_string = filename.split("-")[1][:-2]
    datetime_obj = datetime.strptime(datetime_string, "%Y%m%d%H%M")
    return convert_utc_to_bst(datetime_obj).date()


def persist_daily_sorted_letter_counts(day, file_name, sorted_letter_counts):
    daily_letter_count = DailySortedLetter(
        billing_day=day,
        file_name=file_name,
        unsorted_count=sorted_letter_counts["unsorted"],
        sorted_count=sorted_letter_counts["sorted"],
    )
    dao_create_or_update_daily_sorted_letter(daily_letter_count)


def process_updates_from_file(response_file):
    NotificationUpdate = namedtuple("NotificationUpdate", ["reference", "status", "page_count", "cost_threshold"])
    notification_updates = [NotificationUpdate(*line.split("|")) for line in response_file.splitlines()]
    return notification_updates


def update_letter_notification(filename, temporary_failures, update):
    if update.status == DVLA_RESPONSE_STATUS_SENT:
        status = NOTIFICATION_DELIVERED
    else:
        status = NOTIFICATION_TEMPORARY_FAILURE
        temporary_failures.append(update.reference)

    updated_count, _ = dao_update_notifications_by_reference(
        references=[update.reference], update_dict={"status": status, "updated_at": datetime.utcnow()}
    )

    if not updated_count:
        msg = (
            "Update letter notification file {filename} failed: notification either not found "
            "or already updated from delivered. Status {status} for notification reference {reference}".format(
                filename=filename, status=status, reference=update.reference
            )
        )
        current_app.logger.info(msg)


def check_billable_units(notification_update):
    notification = dao_get_notification_or_history_by_reference(notification_update.reference)

    if int(notification_update.page_count) != notification.billable_units:
        msg = "Notification with id {} has {} billable_units but DVLA says page count is {}".format(
            notification.id, notification.billable_units, notification_update.page_count
        )
        try:
            raise DVLAException(msg)
        except DVLAException:
            current_app.logger.exception(msg)


@notify_celery.task(bind=True, name="send-inbound-sms", max_retries=5, default_retry_delay=300)
def send_inbound_sms_to_service(self, inbound_sms_id, service_id):
    inbound_api = get_service_inbound_api_for_service(service_id=service_id)
    if not inbound_api:
        # No API data has been set for this service
        return

    inbound_sms = dao_get_inbound_sms_by_id(service_id=service_id, inbound_id=inbound_sms_id)
    data = {
        "id": str(inbound_sms.id),
        # TODO: should we be validating and formatting the phone number here?
        "source_number": inbound_sms.user_number,
        "destination_number": inbound_sms.notify_number,
        "message": inbound_sms.content,
        "date_received": inbound_sms.provider_date.strftime(DATETIME_FORMAT),
    }

    try:
        response = request(
            method="POST",
            url=inbound_api.url,
            data=json.dumps(data),
            headers={"Content-Type": "application/json", "Authorization": "Bearer {}".format(inbound_api.bearer_token)},
            timeout=60,
        )
        current_app.logger.debug(
            f"send_inbound_sms_to_service sending {inbound_sms_id} to {inbound_api.url}, "
            + f"response {response.status_code}"
        )
        response.raise_for_status()
    except RequestException as e:
        current_app.logger.warning(
            f"send_inbound_sms_to_service failed for service_id: {service_id} for inbound_sms_id: {inbound_sms_id} "
            + f"and url: {inbound_api.url}. exception: {e}"
        )
        if not isinstance(e, HTTPError) or e.response.status_code >= 500:
            try:
                self.retry(queue=QueueNames.RETRY)
            except self.MaxRetriesExceededError:
                current_app.logger.error(
                    "Retry: send_inbound_sms_to_service has retried the max number of"
                    + f"times for service: {service_id} and inbound_sms {inbound_sms_id}"
                )
        else:
            current_app.logger.warning(
                f"send_inbound_sms_to_service is not being retried for service_id: {service_id} for "
                + f"inbound_sms id: {inbound_sms_id} and url: {inbound_api.url}. exception: {e}"
            )


@notify_celery.task(name="process-incomplete-jobs")
def process_incomplete_jobs(job_ids):
    jobs = [dao_get_job_by_id(job_id) for job_id in job_ids]

    # reset the processing start time so that the check_job_status scheduled task doesn't pick this job up again
    for job in jobs:
        job.job_status = JOB_STATUS_IN_PROGRESS
        job.processing_started = datetime.utcnow()
        dao_update_job(job)

    current_app.logger.info("Resuming Job(s) {}".format(job_ids))
    for job_id in job_ids:
        process_incomplete_job(job_id)


def process_incomplete_job(job_id):
    job = dao_get_job_by_id(job_id)

    last_notification_added = dao_get_last_notification_added_for_job_id(job_id)

    if last_notification_added:
        resume_from_row = last_notification_added.job_row_number
    else:
        resume_from_row = -1  # The first row in the csv with a number is row 0

    current_app.logger.info("Resuming job {} from row {}".format(job_id, resume_from_row))

    recipient_csv, template, sender_id = get_recipient_csv_and_template_and_sender_id(job)

    for row in recipient_csv.get_rows():
        if row.index > resume_from_row:
            process_row(row, template, job, job.service, sender_id=sender_id)

    job_complete(job, resumed=True)


@notify_celery.task(name="process-returned-letters-list")
def process_returned_letters_list(notification_references):
    updated, updated_history = dao_update_notifications_by_reference(
        notification_references, {"status": NOTIFICATION_RETURNED_LETTER}
    )

    insert_or_update_returned_letters(notification_references)

    current_app.logger.info(
        "Updated {} letter notifications ({} history notifications, from {} references) to returned-letter".format(
            updated, updated_history, len(notification_references)
        )
    )
