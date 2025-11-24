import logging
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from botocore.exceptions import ClientError as BotoClientError
from flask import current_app
from notifications_utils.insensitive_dict import InsensitiveDict
from notifications_utils.recipient_validation.errors import InvalidPhoneError
from notifications_utils.recipient_validation.postal_address import PostalAddress
from notifications_utils.recipients import RecipientCSV
from sqlalchemy.exc import SQLAlchemyError

from app import create_random_identifier, create_uuid, notify_celery, signing
from app.aws import s3
from app.celery import letters_pdf_tasks, provider_tasks
from app.celery.service_callback_tasks import create_returned_letter_callback_data, send_returned_letter_to_service
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
    NOTIFICATION_VALIDATION_FAILED,
    REPORT_REQUEST_FAILED,
    REPORT_REQUEST_IN_PROGRESS,
    REPORT_REQUEST_PENDING,
    REPORT_REQUEST_STORED,
    SMS_TYPE,
)
from app.dao.jobs_dao import dao_get_job_by_id, dao_update_job
from app.dao.notifications_dao import (
    dao_get_last_notification_added_for_job_id,
    dao_get_unknown_references,
    dao_update_notifications_by_reference,
    get_notification_by_id,
)
from app.dao.report_requests_dao import dao_get_report_request_by_id, dao_update_report_request
from app.dao.returned_letters_dao import _get_notification_ids_for_references, insert_returned_letters
from app.dao.service_callback_api_dao import get_returned_letter_callback_api_for_service
from app.dao.service_email_reply_to_dao import dao_get_reply_to_by_id
from app.dao.service_sms_sender_dao import dao_get_service_sms_senders_by_id
from app.dao.templates_dao import dao_get_template_by_id
from app.notifications.process_notifications import persist_notification
from app.notifications.validators import (
    check_service_over_daily_message_limit,
    validate_and_format_recipient,
)
from app.report_requests.process_notifications_report import ReportRequestProcessor
from app.serialised_models import SerialisedService, SerialisedTemplate
from app.service.utils import service_allowed_to_send_to
from app.utils import batched
from app.v2.errors import TooManyRequestsError

DEFAULT_SHATTER_JOB_ROWS_BATCH_SIZE = 32


class UnprocessableJobRow(Exception):
    pass


class ProcessReportRequestException(Exception):
    pass


@notify_celery.task(name="process-job")
def process_job(job_id, sender_id=None, shatter_batch_size=DEFAULT_SHATTER_JOB_ROWS_BATCH_SIZE):
    start = datetime.utcnow()
    job = dao_get_job_by_id(job_id)
    current_app.logger.info(
        "Starting process-job task for job id %s with status: %s",
        job_id,
        job.job_status,
        extra={"job_id": job_id, "job_status": job.job_status},
    )

    if job.job_status != JOB_STATUS_PENDING:
        return

    service = job.service

    job.job_status = JOB_STATUS_IN_PROGRESS
    job.processing_started = start
    dao_update_job(job)

    if not service.active:
        job.job_status = JOB_STATUS_CANCELLED
        dao_update_job(job)
        current_app.logger.warning(
            "Job %s has been cancelled, service %s is inactive",
            job_id,
            service.id,
            extra={"job_id": job_id, "service_id": service.id},
        )
        return

    if __sending_limits_for_job_exceeded(service, job, job_id):
        return

    recipient_csv, template, sender_id = get_recipient_csv_and_template_and_sender_id(job)

    current_app.logger.info(
        "Starting job %s processing %s notifications",
        job_id,
        job.notification_count,
        extra={"job_id": job_id, "notification_count": job.notification_count},
    )

    for shatter_batch in batched(recipient_csv.get_rows(), n=shatter_batch_size):
        batch_args_kwargs = [
            get_id_task_args_kwargs_for_job_row(row, template, job, service, sender_id=sender_id)[1]
            for row in shatter_batch
        ]
        _shatter_job_rows_with_subdivision(template.template_type, batch_args_kwargs)

    job_complete(job, start=start)


def _shatter_job_rows_with_subdivision(template_type, args_kwargs_seq, top_level=True):
    try:
        shatter_job_rows.apply_async(
            (
                template_type,
                args_kwargs_seq,
            ),
            queue=QueueNames.JOBS,
        )
    except BotoClientError as e:
        # this information is helpfully not preserved outside the message string of the exception, so
        # we don't really have any option but to sniff it
        if "InvalidParameterValue" not in str(e):
            # this is not the exception we are looking for
            raise

        # else we'll assume this is a failure to send the SQS message due to its size, so split the
        # batch in two and try again with each half

        split_batch_size = len(args_kwargs_seq) // 2
        if split_batch_size < 1:
            # can't divide any further
            raise UnprocessableJobRow from e

        for sub_batch in (args_kwargs_seq[:split_batch_size], args_kwargs_seq[split_batch_size:]):
            _shatter_job_rows_with_subdivision(template_type, sub_batch, top_level=False)

    else:
        if not top_level:
            log_context = {"shatter_batch_size": len(args_kwargs_seq)}
            current_app.logger.info(
                "Job shatter batch sent with reduced size of %(shatter_batch_size)s", log_context, extra=log_context
            )


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

    extra = {"job_id": job.id, "job_processing_finished_at": job.processing_finished}
    if resumed:
        current_app.logger.info(
            "Resumed Job %(job_id)s completed at %(job_processing_finished_at)s", extra, extra=extra
        )
    else:
        extra = {
            "job_created_at": job.created_at,
            "job_started_at": start,
            **extra,
        }
        current_app.logger.info(
            "Job %(job_id)s created at %(job_created_at)s started at %(job_started_at)s "
            "finished at %(job_processing_finished_at)s",
            extra,
            extra=extra,
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
        extra = {
            "job_id": job_id,
            "notification_count": job.notification_count,
            "limit_name": e.limit_name,
            "sending_limit": e.sending_limit,
        }
        current_app.logger.info(
            "Job %(job_id)s size %(notification_count)s error. Sending limits (%(limit_name)s: "
            "%(sending_limit)s) exceeded.",
            extra,
            extra=extra,
        )
        return True

    return False


@notify_celery.task(bind=True, name="save-sms", max_retries=5, default_retry_delay=300)
def save_sms(
    self,
    service_id,
    notification_id,
    encoded_notification,
    sender_id=None,
):
    notification = signing.decode(encoded_notification)
    service = SerialisedService.from_id(service_id)
    template = SerialisedTemplate.from_id_service_id_and_version(
        notification["template"],
        service_id=service.id,
        version=notification["template_version"],
    )

    if sender_id:
        reply_to_text = dao_get_service_sms_senders_by_id(service_id, sender_id).sms_sender
    else:
        reply_to_text = template.reply_to_text

    if not service_allowed_to_send_to(notification["to"], service, KEY_TYPE_NORMAL):
        extra = {
            "notification_id": notification_id,
            "job_id": notification.get("job", None),
            "job_row_number": notification.get("row_number", None),
        }
        current_app.logger.warning(
            "SMS notification %(notification_id)s for job %(job_id)s failed as restricted service",
            extra,
            extra=extra,
        )
        return

    try:
        recipient_data = validate_and_format_recipient(
            send_to=notification["to"],
            key_type=KEY_TYPE_NORMAL,
            service=service,
            notification_type=SMS_TYPE,
            check_intl_sms_limit=False,
        )
        extra_args = {}

    except InvalidPhoneError:
        recipient_data = {
            "unformatted_recipient": notification["to"],
            "normalised_to": notification["to"],
            "international": False,
            "phone_prefix": "+44",
            "rate_multiplier": 0,
        }
        extra_args = {
            "status": NOTIFICATION_VALIDATION_FAILED,
            "billable_units": 0,
            "updated_at": datetime.utcnow(),
        }

    try:
        saved_notification = persist_notification(
            template_id=notification["template"],
            template_version=notification["template_version"],
            recipient=recipient_data,
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
            **extra_args,
        )

        if saved_notification.status != NOTIFICATION_VALIDATION_FAILED:
            provider_tasks.deliver_sms.apply_async(
                [str(saved_notification.id)],
                queue=QueueNames.SEND_SMS,
            )
        else:
            extra = {
                "notification_id": saved_notification.id,
                "job_id": notification.get("job", None),
                "job_row_number": notification.get("row_number", None),
            }
            current_app.logger.warning(
                "SMS notification %(notification_id)s for job %(job_id)s has failed validation and will not be sent",
                extra,
                extra=extra,
            )

        extra = {
            "notification_id": saved_notification.id,
            "notification_created_at": saved_notification.created_at,
            "job_id": notification.get("job", None),
            "job_row_number": notification.get("row_number", None),
        }
        current_app.logger.info(
            "Saving SMS notification %(notification_id)s created_at %(notification_created_at)s for job %(job_id)s",
            extra,
            extra=extra,
        )

    except SQLAlchemyError as e:
        handle_exception(self, notification, notification_id, e)


@notify_celery.task(bind=True, name="save-email", max_retries=5, default_retry_delay=300)
def save_email(self, service_id, notification_id, encoded_notification, sender_id=None, early_log_level=logging.DEBUG):
    notification = signing.decode(encoded_notification)

    service = SerialisedService.from_id(service_id)
    template = SerialisedTemplate.from_id_service_id_and_version(
        notification["template"],
        service_id=service.id,
        version=notification["template_version"],
    )

    if sender_id:
        reply_to_text = dao_get_reply_to_by_id(reply_to_id=sender_id, service_id=service_id).email_address
    else:
        reply_to_text = template.reply_to_text

    if not service_allowed_to_send_to(notification["to"], service, KEY_TYPE_NORMAL):
        extra = {
            "notification_id": notification_id,
            "job_id": notification.get("job", None),
            "job_row_number": notification.get("row_number", None),
        }
        current_app.logger.warning(
            "Email notification %(notification_id)s for job %(job_id)s failed as restricted service",
            extra,
            extra=extra,
        )
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

        extra = {
            "notification_id": saved_notification.id,
            "notification_created_at": saved_notification.created_at,
            "job_id": notification.get("job", None),
            "job_row_number": notification.get("row_number", None),
        }
        current_app.logger.info(
            "Saving Email notification %(notification_id)s created_at %(notification_created_at)s for job %(job_id)s",
            extra,
            extra=extra,
        )
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
    template = SerialisedTemplate.from_id_service_id_and_version(
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

        extra = {
            "notification_id": saved_notification.id,
            "notification_created_at": saved_notification.created_at,
            "job_id": notification.get("job", None),
            "job_row_number": notification.get("row_number", None),
        }
        current_app.logger.info(
            "Saving Letter notification %(notification_id)s created_at %(notification_created_at)s for job %(job_id)s",
            extra,
            extra=extra,
        )
    except SQLAlchemyError as e:
        handle_exception(self, notification, notification_id, e)


def handle_exception(task, notification, notification_id, exc):
    if not get_notification_by_id(notification_id):
        extra = {
            "notification_id": notification_id,
            "celery_task": task.name,
            "job_id": notification.get("job", None),
            "job_row_number": notification.get("row_number", None),
        }
        base_msg = (
            "task %(celery_task)s notification for job %(job_id)s row number %(job_row_number)s "
            "and notification id %(notification_id)s"
        )
        # Sometimes, SQS plays the same message twice. We should be able to catch an IntegrityError, but it seems
        # SQLAlchemy is throwing a FlushError. So we check if the notification id already exists then do not
        # send to the retry queue.
        current_app.logger.exception("Retry: " + base_msg, extra, extra=extra)  # noqa
        try:
            task.retry(queue=QueueNames.RETRY, exc=exc)
        except task.MaxRetriesExceededError:
            current_app.logger.error("Max retry failed: " + base_msg, extra, extra=extra)  # noqa


@notify_celery.task(name="process-incomplete-jobs")
def process_incomplete_jobs(job_ids, shatter_batch_size=DEFAULT_SHATTER_JOB_ROWS_BATCH_SIZE):
    jobs = [dao_get_job_by_id(job_id) for job_id in job_ids]

    # reset the processing start time so that the check_job_status scheduled task doesn't pick this job up again
    for job in jobs:
        job.job_status = JOB_STATUS_IN_PROGRESS
        job.processing_started = datetime.utcnow()
        dao_update_job(job)

    for job_id in job_ids:
        current_app.logger.info("Resuming job %s", job_id, extra={"job_id": job_id})
        try:
            process_incomplete_job(job_id, shatter_batch_size=shatter_batch_size)
        except UnprocessableJobRow as e:
            current_app.logger.exception(str(e), extra={"job_id": job_id})
            # but continue to next job


def process_incomplete_job(job_id, shatter_batch_size=DEFAULT_SHATTER_JOB_ROWS_BATCH_SIZE):
    job = dao_get_job_by_id(job_id)

    last_notification_added = dao_get_last_notification_added_for_job_id(job_id)

    if last_notification_added:
        resume_from_row = last_notification_added.job_row_number
    else:
        resume_from_row = -1  # The first row in the csv with a number is row 0

    current_app.logger.info(
        "Resuming job %s from row %s",
        job_id,
        resume_from_row,
        extra={"job_id": job_id, "job_row_number": resume_from_row},
    )

    recipient_csv, template, sender_id = get_recipient_csv_and_template_and_sender_id(job)

    for shatter_batch in batched(
        (row for row in recipient_csv.get_rows() if row.index > resume_from_row),
        n=shatter_batch_size,
    ):
        batch_args_kwargs = [
            get_id_task_args_kwargs_for_job_row(row, template, job, job.service, sender_id=sender_id)[1]
            for row in shatter_batch
        ]
        _shatter_job_rows_with_subdivision(template.template_type, batch_args_kwargs)

    job_complete(job, resumed=True)


@notify_celery.task(name="process-returned-letters-list")
def process_returned_letters_list(notification_references):
    for ref in dao_get_unknown_references(notification_references):
        current_app.logger.warning(
            "Notification with reference %s not found in notifications or notifications history",
            ref,
            extra={"notification_reference": ref},
        )

    updated, updated_history = dao_update_notifications_by_reference(
        notification_references, {"status": NOTIFICATION_RETURNED_LETTER}
    )

    insert_returned_letters(notification_references)

    extra = {
        "updated_record_count": updated,
        "updated_history_record_count": updated_history,
        "notification_reference_count": len(notification_references),
    }
    current_app.logger.info(
        "Updated %(updated_record_count)s letter notifications (%(updated_history_record_count)s "
        "history notifications, from %(notification_reference_count)s references) to returned-letter",
        extra,
        extra=extra,
    )

    _process_returned_letters_callback(notification_references)


def _process_returned_letters_callback(notification_references):
    data = _get_notification_ids_for_references(notification_references)
    for row in data:
        _check_and_queue_returned_letter_callback_task(row.id, row.service_id)


def _check_and_queue_returned_letter_callback_task(notification_id, service_id):
    # queue callback task only if the service_callback_api exists
    if service_callback_api := get_returned_letter_callback_api_for_service(service_id=service_id):
        returned_letter_data = create_returned_letter_callback_data(notification_id, service_id, service_callback_api)
        send_returned_letter_to_service.apply_async([returned_letter_data], queue=QueueNames.CALLBACKS)


@notify_celery.task(bind=True, name="process-report-request")
def process_report_request(self, service_id, report_request_id):
    report_request = dao_get_report_request_by_id(service_id=UUID(service_id), report_id=UUID(report_request_id))

    extra = {
        "report_request_id": report_request_id,
        "report_request_status": report_request.status,
        "celery_task": self.name,
    }
    current_app.logger.info(
        "Starting %(celery_task)s task for report request id %(report_request_id)s and "
        "status %(report_request_status)s",
        extra,
        extra=extra,
    )

    if report_request.status != REPORT_REQUEST_PENDING:
        return

    report_request.status = REPORT_REQUEST_IN_PROGRESS
    dao_update_report_request(report_request)

    try:
        ReportRequestProcessor(service_id=service_id, report_request_id=report_request_id).process()
        report_request.status = REPORT_REQUEST_STORED
        dao_update_report_request(report_request)

        current_app.logger.info(
            "Report request %s succeeded", report_request_id, extra={"report_request_id": report_request_id}
        )
    except Exception as e:
        report_request.status = REPORT_REQUEST_FAILED
        dao_update_report_request(report_request)
        raise ProcessReportRequestException(f"Report request for id {report_request_id} failed") from e
