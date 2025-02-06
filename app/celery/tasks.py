from collections.abc import Sequence
from datetime import datetime

from flask import current_app
from notifications_utils.insensitive_dict import InsensitiveDict
from notifications_utils.recipient_validation.postal_address import PostalAddress
from notifications_utils.recipients import RecipientCSV
from sqlalchemy.exc import SQLAlchemyError

from app import create_random_identifier, create_uuid, notify_celery, signing
from app.aws import s3
from app.celery import letters_pdf_tasks, provider_tasks
from app.config import QueueNames
from app.constants import (
    EMAIL_TYPE,
    JOB_STATUS_CANCELLED,
    JOB_STATUS_FINISHED,
    JOB_STATUS_IN_PROGRESS,
    JOB_STATUS_PENDING,
    KEY_TYPE_NORMAL,
    LETTER_TYPE,
    NOTIFICATION_CREATED,
    NOTIFICATION_RETURNED_LETTER,
    SMS_TYPE,
)
from app.dao.jobs_dao import dao_get_job_by_id, dao_update_job
from app.dao.notifications_dao import (
    dao_get_last_notification_added_for_job_id,
    dao_update_notifications_by_reference,
    get_notification_by_id,
)
from app.dao.returned_letters_dao import _get_notification_ids_for_references, insert_returned_letters
from app.dao.service_email_reply_to_dao import dao_get_reply_to_by_id
from app.dao.service_sms_sender_dao import dao_get_service_sms_senders_by_id
from app.dao.templates_dao import dao_get_template_by_id
from app.notifications.process_notifications import persist_notification
from app.notifications.validators import check_service_over_daily_message_limit
from app.serialised_models import SerialisedService, SerialisedTemplate
from app.service.utils import service_allowed_to_send_to
from app.utils import batched
from app.v2.errors import TooManyRequestsError

DEFAULT_SHATTER_JOB_ROWS_BATCH_SIZE = 32


@notify_celery.task(name="process-job")
def process_job(job_id, sender_id=None, shatter_batch_size=DEFAULT_SHATTER_JOB_ROWS_BATCH_SIZE):
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

    for shatter_batch in batched(recipient_csv.get_rows(), n=shatter_batch_size):
        batch_args_kwargs = [
            get_id_task_args_kwargs_for_job_row(row, template, job, service, sender_id=sender_id)[1]
            for row in shatter_batch
        ]
        shatter_job_rows.apply_async(
            (
                template.template_type,
                batch_args_kwargs,
            ),
            queue=QueueNames.JOBS,
        )

    job_complete(job, start=start)


@notify_celery.task(name="shatter-job-rows")
def shatter_job_rows(
    template_type: str,
    args_kwargs_seq: Sequence,
):
    for task_args_kwargs in args_kwargs_seq:
        process_job_row(template_type, task_args_kwargs)


def process_job_row(template_type, task_args_kwargs):
    send_fn = {
        SMS_TYPE: save_sms,
        EMAIL_TYPE: save_email,
        LETTER_TYPE: save_letter,
    }[template_type]

    send_fn.apply_async(
        *task_args_kwargs,
        queue=QueueNames.DATABASE,
    )


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


def get_id_task_args_kwargs_for_job_row(row, template, job, service, sender_id=None):
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

    notification_id = create_uuid()
    task_args = (
        str(service.id),
        notification_id,
        encoded,
    )

    task_kwargs = {}
    if sender_id:
        task_kwargs["sender_id"] = sender_id

    return notification_id, (task_args, task_kwargs)


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


@notify_celery.task(name="process-incomplete-jobs")
def process_incomplete_jobs(job_ids, shatter_batch_size=DEFAULT_SHATTER_JOB_ROWS_BATCH_SIZE):
    jobs = [dao_get_job_by_id(job_id) for job_id in job_ids]

    # reset the processing start time so that the check_job_status scheduled task doesn't pick this job up again
    for job in jobs:
        job.job_status = JOB_STATUS_IN_PROGRESS
        job.processing_started = datetime.utcnow()
        dao_update_job(job)

    current_app.logger.info("Resuming job(s) %s", job_ids)
    for job_id in job_ids:
        process_incomplete_job(job_id, shatter_batch_size=shatter_batch_size)


def process_incomplete_job(job_id, shatter_batch_size=DEFAULT_SHATTER_JOB_ROWS_BATCH_SIZE):
    job = dao_get_job_by_id(job_id)

    last_notification_added = dao_get_last_notification_added_for_job_id(job_id)

    if last_notification_added:
        resume_from_row = last_notification_added.job_row_number
    else:
        resume_from_row = -1  # The first row in the csv with a number is row 0

    current_app.logger.info("Resuming job %s from row %s", job_id, resume_from_row)

    recipient_csv, template, sender_id = get_recipient_csv_and_template_and_sender_id(job)

    for shatter_batch in batched(
        (row for row in recipient_csv.get_rows() if row.index > resume_from_row),
        n=shatter_batch_size,
    ):
        batch_args_kwargs = [
            get_id_task_args_kwargs_for_job_row(row, template, job, job.service, sender_id=sender_id)[1]
            for row in shatter_batch
        ]
        shatter_job_rows.apply_async(
            (
                template.template_type,
                batch_args_kwargs,
            ),
            queue=QueueNames.JOBS,
        )

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

    _process_returned_letters_callback(notification_references)


def _process_returned_letters_callback(notification_references):
    data = _get_notification_ids_for_references(notification_references)
    for row in data:
        _check_and_queue_returned_letter_callback_task(row.id, row.service_id)


def _check_and_queue_returned_letter_callback_task(notification_id, service_id):
    pass
