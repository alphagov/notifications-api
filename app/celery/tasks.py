from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from flask import current_app
from notifications_utils.insensitive_dict import InsensitiveDict
from notifications_utils.recipient_validation.postal_address import PostalAddress
from notifications_utils.recipients import RecipientCSV
from notifications_utils.timezones import convert_utc_to_bst
from sqlalchemy.exc import SQLAlchemyError

from app import create_random_identifier, create_uuid, notify_celery, signing
from app.aws import s3
from app.celery import letters_pdf_tasks, provider_tasks
from app.config import QueueNames
from app.constants import (
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
    NOTIFICATION_TEMPORARY_FAILURE,
    SMS_TYPE,
)
from app.dao.daily_sorted_letter_dao import (
    dao_create_or_update_daily_sorted_letter,
)
from app.dao.jobs_dao import dao_get_job_by_id, dao_update_job
from app.dao.notifications_dao import (
    dao_get_last_notification_added_for_job_id,
    dao_get_notification_or_history_by_reference,
    dao_record_letter_despatched_on,
    dao_update_notifications_by_reference,
    get_notification_by_id,
)
from app.dao.returned_letters_dao import insert_returned_letters
from app.dao.service_email_reply_to_dao import dao_get_reply_to_by_id
from app.dao.service_sms_sender_dao import dao_get_service_sms_senders_by_id
from app.dao.templates_dao import dao_get_template_by_id
from app.exceptions import DVLAException
from app.models import DailySortedLetter, LetterCostThreshold
from app.notifications.process_notifications import persist_notification
from app.notifications.validators import check_service_over_daily_message_limit
from app.serialised_models import SerialisedService, SerialisedTemplate
from app.service.utils import service_allowed_to_send_to
from app.v2.errors import TooManyRequestsError


@notify_celery.task(name="process-job")
def process_job(job_id, sender_id=None):
    start = datetime.utcnow()
    job = dao_get_job_by_id(job_id)
    current_app.logger.info("Starting process-job task for job id %s with status: %s", job_id, job.job_status)

    if job.job_status != JOB_STATUS_PENDING:
        return

    service = job.service

    job.job_status = JOB_STATUS_IN_PROGRESS
    job.processing_started = start
    dao_update_job(job)

    if not service.active:
        job.job_status = JOB_STATUS_CANCELLED
        dao_update_job(job)
        current_app.logger.warning("Job %s has been cancelled, service %s is inactive", job_id, service.id)
        return

    if __sending_limits_for_job_exceeded(service, job, job_id):
        return

    recipient_csv, template, sender_id = get_recipient_csv_and_template_and_sender_id(job)

    current_app.logger.info("Starting job %s processing %s notifications", job_id, job.notification_count)

    for row in recipient_csv.get_rows():
        process_row(row, template, job, service, sender_id=sender_id)

    job_complete(job, start=start)


def job_complete(job, resumed=False, start=None):
    job.job_status = JOB_STATUS_FINISHED

    finished = datetime.utcnow()
    job.processing_finished = finished
    dao_update_job(job)

    if resumed:
        current_app.logger.info("Resumed Job %s completed at %s", job.id, job.processing_finished)
    else:
        current_app.logger.info(
            "Job %s created at %s started at %s finished at %s", job.id, job.created_at, start, finished
        )


def get_recipient_csv_and_template_and_sender_id(job):
    db_template = dao_get_template_by_id(job.template_id, job.template_version)
    template = db_template._as_utils_template()

    contents, meta_data = s3.get_job_and_metadata_from_s3(service_id=str(job.service_id), job_id=str(job.id))
    recipient_csv = RecipientCSV(contents, template=template)

    return recipient_csv, template, meta_data.get("sender_id")


def process_row(row, template, job, service, sender_id=None):
    template_type = template.template_type
    encoded = signing.encode(
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
            encoded,
        ),
        task_kwargs,
        queue=QueueNames.DATABASE,
    )
    return notification_id


def __sending_limits_for_job_exceeded(service, job, job_id):
    try:
        check_service_over_daily_message_limit(
            service,
            KEY_TYPE_NORMAL,
            notification_type=job.template.template_type,
            num_notifications=job.notification_count,
        )

    except TooManyRequestsError as e:
        job.job_status = "sending limits exceeded"
        job.processing_finished = datetime.utcnow()
        dao_update_job(job)
        current_app.logger.info(
            "Job %s size %s error. Sending limits (%s: %s) exceeded.",
            job_id,
            job.notification_count,
            e.limit_name,
            e.sending_limit,
        )
        return True

    return False


@notify_celery.task(bind=True, name="save-sms", max_retries=5, default_retry_delay=300)
def save_sms(self, service_id, notification_id, encoded_notification, sender_id=None):
    notification = signing.decode(encoded_notification)
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
        current_app.logger.debug("SMS %s failed as restricted service", notification_id)
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
            queue=QueueNames.SEND_SMS,
        )

        current_app.logger.debug(
            "SMS %s created at %s for job %s",
            saved_notification.id,
            saved_notification.created_at,
            notification.get("job", None),
        )

    except SQLAlchemyError as e:
        handle_exception(self, notification, notification_id, e)


@notify_celery.task(bind=True, name="save-email", max_retries=5, default_retry_delay=300)
def save_email(self, service_id, notification_id, encoded_notification, sender_id=None):
    notification = signing.decode(encoded_notification)

    service = SerialisedService.from_id(service_id)
    template = SerialisedTemplate.from_id_and_service_id(
        notification["template"],
        service_id=service.id,
        version=notification["template_version"],
    )

    if sender_id:
        reply_to_text = dao_get_reply_to_by_id(reply_to_id=sender_id, service_id=service_id).email_address
    else:
        reply_to_text = template.reply_to_text

    if not service_allowed_to_send_to(notification["to"], service, KEY_TYPE_NORMAL):
        current_app.logger.info("Email %s failed as restricted service", notification_id)
        return

    try:
        saved_notification = persist_notification(
            template_id=notification["template"],
            template_version=notification["template_version"],
            template_has_unsubscribe_link=template.has_unsubscribe_link,
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
            queue=QueueNames.SEND_EMAIL,
        )

        current_app.logger.debug("Email %s created at %s", saved_notification.id, saved_notification.created_at)
    except SQLAlchemyError as e:
        handle_exception(self, notification, notification_id, e)


@notify_celery.task(bind=True, name="save-letter", max_retries=5, default_retry_delay=300)
def save_letter(
    self,
    service_id,
    notification_id,
    encoded_notification,
):
    notification = signing.decode(encoded_notification)

    postal_address = PostalAddress.from_personalisation(InsensitiveDict(notification["personalisation"]))

    service = SerialisedService.from_id(service_id)
    template = SerialisedTemplate.from_id_and_service_id(
        notification["template"],
        service_id=service.id,
        version=notification["template_version"],
    )

    try:
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
            status=NOTIFICATION_CREATED,
        )

        letters_pdf_tasks.get_pdf_for_templated_letter.apply_async(
            [str(saved_notification.id)], queue=QueueNames.CREATE_LETTERS_PDF
        )

        current_app.logger.debug("Letter %s created at %s", saved_notification.id, saved_notification.created_at)
    except SQLAlchemyError as e:
        handle_exception(self, notification, notification_id, e)


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
        current_app.logger.exception("Retry %s", retry_msg)
        try:
            task.retry(queue=QueueNames.RETRY, exc=exc)
        except task.MaxRetriesExceededError:
            current_app.logger.error("Max retry failed %s", retry_msg)


@notify_celery.task(bind=True, name="update-letter-notifications-statuses")
def update_letter_notifications_statuses(self, filename):
    current_app.logger.info("update_letter_notifications_statuses has started for filename %s", filename)
    notification_updates = parse_dvla_file(filename)

    temporary_failures = []

    for update in notification_updates:
        check_billable_units(update)
        update_letter_notification(filename, temporary_failures, update)
    if temporary_failures:
        # This will alert Notify that DVLA was unable to deliver the letters, we need to investigate
        message = f"DVLA response file: {filename} has failed letters with notification.reference {temporary_failures}"
        raise DVLAException(message)
    current_app.logger.info("update_letter_notifications_statuses has finished for filename %s", filename)


@notify_celery.task(bind=True, name="record-daily-sorted-counts")
def record_daily_sorted_counts(self, filename):
    current_app.logger.info("record_daily_sorted_counts has started for filename %s", filename)
    sorted_letter_counts = defaultdict(int)
    notification_updates = parse_dvla_file(filename)
    for update in notification_updates:
        sorted_letter_counts[update.cost_threshold.value] += 1

    billing_date = get_billing_date_in_bst_from_filename(filename)
    persist_daily_sorted_letter_counts(day=billing_date, file_name=filename, sorted_letter_counts=sorted_letter_counts)
    current_app.logger.info("record_daily_sorted_counts has finished for filename %s", filename)


def parse_dvla_file(filename):
    bucket_location = "{}-ftp".format(current_app.config["NOTIFY_EMAIL_DOMAIN"])
    response_file_content = s3.get_s3_file(bucket_location, filename)
    return process_updates_from_file(response_file_content, filename=filename)


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


@dataclass
class NotificationUpdate:
    reference: str
    status: str
    page_count: str
    cost_threshold: LetterCostThreshold
    despatch_date: str


def process_updates_from_file(response_file, filename):
    notification_updates = []
    invalid_statuses = set()

    for line in response_file.splitlines():
        try:
            reference, status, page_count, raw_cost_threshold, despatch_date = line.split("|")
        except ValueError as e:
            raise DVLAException(f"DVLA response file: {filename} has an invalid format") from e

        try:
            cost_threshold = LetterCostThreshold(raw_cost_threshold.lower())
        except ValueError:
            invalid_statuses.add(raw_cost_threshold.lower())
            continue

        notification_updates.append(
            NotificationUpdate(
                reference=reference,
                status=status,
                page_count=page_count,
                cost_threshold=cost_threshold,
                despatch_date=despatch_date,
            )
        )

    if invalid_statuses:
        raise DVLAException(f"DVLA response file: {filename} contains unknown Sorted status {invalid_statuses}")

    return notification_updates


def update_letter_notification(filename: str, temporary_failures: list, update: NotificationUpdate):
    if update.status == DVLA_RESPONSE_STATUS_SENT:
        status = NOTIFICATION_DELIVERED
    else:
        status = NOTIFICATION_TEMPORARY_FAILURE
        temporary_failures.append(update.reference)

    updated_count, _ = dao_update_notifications_by_reference(
        references=[update.reference], update_dict={"status": status, "updated_at": datetime.utcnow()}
    )
    dao_record_letter_despatched_on(
        reference=update.reference, despatched_on=update.despatch_date, cost_threshold=update.cost_threshold
    )

    if not updated_count:
        current_app.logger.info(
            "Update letter notification file %s failed: notification either not found "
            "or already updated from delivered. Status %s for notification reference %s",
            filename,
            status,
            update.reference,
        )


def check_billable_units(notification_update):
    notification = dao_get_notification_or_history_by_reference(notification_update.reference)

    if int(notification_update.page_count) != notification.billable_units:
        current_app.logger.error(
            "Notification with id %s has %s billable_units but DVLA says page count is %s",
            notification.id,
            notification.billable_units,
            notification_update.page_count,
        )


@notify_celery.task(name="process-incomplete-jobs")
def process_incomplete_jobs(job_ids):
    jobs = [dao_get_job_by_id(job_id) for job_id in job_ids]

    # reset the processing start time so that the check_job_status scheduled task doesn't pick this job up again
    for job in jobs:
        job.job_status = JOB_STATUS_IN_PROGRESS
        job.processing_started = datetime.utcnow()
        dao_update_job(job)

    current_app.logger.info("Resuming job(s) %s", job_ids)
    for job_id in job_ids:
        process_incomplete_job(job_id)


def process_incomplete_job(job_id):
    job = dao_get_job_by_id(job_id)

    last_notification_added = dao_get_last_notification_added_for_job_id(job_id)

    if last_notification_added:
        resume_from_row = last_notification_added.job_row_number
    else:
        resume_from_row = -1  # The first row in the csv with a number is row 0

    current_app.logger.info("Resuming job %s from row %s", job_id, resume_from_row)

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

    insert_returned_letters(notification_references)

    current_app.logger.info(
        "Updated %s letter notifications (%s history notifications, from %s references) to returned-letter",
        updated,
        updated_history,
        len(notification_references),
    )
