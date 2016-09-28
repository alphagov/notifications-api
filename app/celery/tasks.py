import itertools
from datetime import (datetime)

from flask import current_app
from notifications_utils.recipients import (
    RecipientCSV,
    allowed_to_send_to
)
from notifications_utils.template import Template
from sqlalchemy.exc import SQLAlchemyError

from app import (
    create_uuid,
    DATETIME_FORMAT,
    notify_celery,
    encryption
)
from app.aws import s3
from app.celery.provider_tasks import send_sms_to_provider, send_email_to_provider
from app.dao.jobs_dao import (
    dao_update_job,
    dao_get_job_by_id
)
from app.dao.notifications_dao import (dao_create_notification)
from app.dao.services_dao import dao_fetch_service_by_id, dao_fetch_todays_stats_for_service
from app.dao.templates_dao import dao_get_template_by_id
from app.models import (
    Notification,
    EMAIL_TYPE,
    SMS_TYPE,
    KEY_TYPE_NORMAL,
    KEY_TYPE_TEST
)
from app.statsd_decorators import statsd


@notify_celery.task(name="process-job")
@statsd(namespace="tasks")
def process_job(job_id):
    start = datetime.utcnow()
    job = dao_get_job_by_id(job_id)

    service = job.service

    total_sent = sum(row.count for row in dao_fetch_todays_stats_for_service(service.id))

    if total_sent + job.notification_count > service.message_limit:
        job.status = 'sending limits exceeded'
        job.processing_finished = datetime.utcnow()
        dao_update_job(job)
        current_app.logger.info(
            "Job {} size {} error. Sending limits {} exceeded".format(
                job_id, job.notification_count, service.message_limit)
        )
        return

    job.status = 'in progress'
    dao_update_job(job)

    template = Template(
        dao_get_template_by_id(job.template_id, job.template_version).__dict__
    )

    for row_number, recipient, personalisation in RecipientCSV(
            s3.get_job_from_s3(str(service.id), str(job_id)),
            template_type=template.template_type,
            placeholders=template.placeholders
    ).enumerated_recipients_and_personalisation:

        encrypted = encryption.encrypt({
            'template': str(template.id),
            'template_version': job.template_version,
            'job': str(job.id),
            'to': recipient,
            'row_number': row_number,
            'personalisation': {
                key: personalisation.get(key)
                for key in template.placeholders
            }
        })

        if template.template_type == SMS_TYPE:
            send_sms.apply_async((
                str(job.service_id),
                create_uuid(),
                encrypted,
                datetime.utcnow().strftime(DATETIME_FORMAT)),
                queue='db-sms' if not service.research_mode else 'research-mode'
            )

        if template.template_type == EMAIL_TYPE:
            send_email.apply_async((
                str(job.service_id),
                create_uuid(),
                encrypted,
                datetime.utcnow().strftime(DATETIME_FORMAT)),
                queue='db-email' if not service.research_mode else 'research-mode'
            )

    finished = datetime.utcnow()
    job.status = 'finished'
    job.processing_started = start
    job.processing_finished = finished
    dao_update_job(job)
    current_app.logger.info(
        "Job {} created at {} started at {} finished at {}".format(job_id, job.created_at, start, finished)
    )


@notify_celery.task(bind=True, name="send-sms", max_retries=5, default_retry_delay=300)
@statsd(namespace="tasks")
def send_sms(self,
             service_id,
             notification_id,
             encrypted_notification,
             created_at,
             api_key_id=None,
             key_type=KEY_TYPE_NORMAL):
    notification = encryption.decrypt(encrypted_notification)
    service = dao_fetch_service_by_id(service_id)

    if not service_allowed_to_send_to(notification['to'], service, key_type):
        current_app.logger.info(
            "SMS {} failed as restricted service".format(notification_id)
        )
        return

    try:
        dao_create_notification(
            Notification.from_api_request(
                created_at, notification, notification_id, service.id, SMS_TYPE, api_key_id, key_type
            )
        )
        send_sms_to_provider.apply_async((service_id, notification_id), queue='send-sms')

        current_app.logger.info(
            "SMS {} created at {}".format(notification_id, created_at)
        )

    except SQLAlchemyError as e:
        current_app.logger.exception("RETRY: send_sms notification {}".format(notification_id), e)
        try:
            raise self.retry(queue="retry", exc=e)
        except self.MaxRetriesExceededError:
            current_app.logger.exception(
                "RETRY FAILED: task send_sms failed for notification {}".format(notification.id),
                e
            )


@notify_celery.task(bind=True, name="send-email", max_retries=5, default_retry_delay=300)
@statsd(namespace="tasks")
def send_email(self, service_id,
               notification_id,
               encrypted_notification,
               created_at,
               api_key_id=None,
               key_type=KEY_TYPE_NORMAL):
    notification = encryption.decrypt(encrypted_notification)
    service = dao_fetch_service_by_id(service_id)

    if not service_allowed_to_send_to(notification['to'], service, key_type):
        current_app.logger.info("Email {} failed as restricted service".format(notification_id))
        return

    try:
        dao_create_notification(
            Notification.from_api_request(
                created_at, notification, notification_id, service.id, EMAIL_TYPE, api_key_id, key_type
            )
        )

        send_email_to_provider.apply_async((service_id, notification_id), queue='send-email')

        current_app.logger.info("Email {} created at {}".format(notification_id, created_at))
    except SQLAlchemyError as e:
        current_app.logger.exception("RETRY: send_email notification {}".format(notification_id), e)
        try:
            raise self.retry(queue="retry", exc=e)
        except self.MaxRetriesExceededError:
            current_app.logger.error(
                "RETRY FAILED: task send_email failed for notification {}".format(notification.id),
                e
            )


def service_allowed_to_send_to(recipient, service, key_type):
    if not service.restricted or key_type == KEY_TYPE_TEST:
        return True

    return allowed_to_send_to(
        recipient,
        itertools.chain.from_iterable(
            [user.mobile_number, user.email_address] for user in service.users
        )
    )
