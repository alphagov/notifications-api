import random

import botocore
from boto3 import resource
from datetime import (datetime)

from flask import current_app
from notifications_utils.recipients import (
    RecipientCSV
)
from notifications_utils.template import SMSMessageTemplate, WithSubjectTemplate, LetterDVLATemplate
from sqlalchemy.exc import SQLAlchemyError
from app import (
    create_uuid,
    DATETIME_FORMAT,
    notify_celery,
    encryption
)
from app.aws import s3
from app.celery import provider_tasks
from app.dao.jobs_dao import (
    dao_update_job,
    dao_get_job_by_id,
    all_notifications_are_created_for_job,
    dao_get_all_notifications_for_job)
from app.dao.notifications_dao import get_notification_by_id
from app.dao.services_dao import dao_fetch_service_by_id, fetch_todays_total_message_count
from app.dao.templates_dao import dao_get_template_by_id
from app.models import (
    EMAIL_TYPE,
    SMS_TYPE,
    LETTER_TYPE,
    KEY_TYPE_NORMAL,
    JOB_STATUS_CANCELLED, JOB_STATUS_PENDING, JOB_STATUS_IN_PROGRESS, JOB_STATUS_FINISHED)
from app.notifications.process_notifications import persist_notification
from app.service.utils import service_allowed_to_send_to
from app.statsd_decorators import statsd


@notify_celery.task(name="process-job")
@statsd(namespace="tasks")
def process_job(job_id):
    start = datetime.utcnow()
    job = dao_get_job_by_id(job_id)

    if job.job_status != JOB_STATUS_PENDING:
        return

    service = job.service

    if not service.active:
        job.job_status = JOB_STATUS_CANCELLED
        dao_update_job(job)
        current_app.logger.warn(
            "Job {} has been cancelled, service {} is inactive".format(job_id, service.id))
        return

    if __sending_limits_for_job_exceeded(service, job, job_id):
        return

    job.job_status = JOB_STATUS_IN_PROGRESS
    dao_update_job(job)

    db_template = dao_get_template_by_id(job.template_id, job.template_version)

    TemplateClass = get_template_class(db_template.template_type)
    template = TemplateClass(db_template.__dict__)

    for row_number, recipient, personalisation in RecipientCSV(
            s3.get_job_from_s3(str(service.id), str(job_id)),
            template_type=template.template_type,
            placeholders=template.placeholders
    ).enumerated_recipients_and_personalisation:
        process_row(row_number, recipient, personalisation, template, job, service)

    finished = datetime.utcnow()
    job.job_status = JOB_STATUS_FINISHED
    job.processing_started = start
    job.processing_finished = finished
    dao_update_job(job)
    current_app.logger.info(
        "Job {} created at {} started at {} finished at {}".format(job_id, job.created_at, start, finished)
    )
    if template.template_type == LETTER_TYPE:
        build_dvla_file.apply_async([str(job.id)], queue='process-job')


def process_row(row_number, recipient, personalisation, template, job, service):
    template_type = template.template_type
    encrypted = encryption.encrypt({
        'template': str(template.id),
        'template_version': job.template_version,
        'job': str(job.id),
        'to': recipient,
        'row_number': row_number,
        'personalisation': dict(personalisation)
    })

    send_fns = {
        SMS_TYPE: send_sms,
        EMAIL_TYPE: send_email,
        LETTER_TYPE: persist_letter
    }

    queues = {
        SMS_TYPE: 'db-sms',
        EMAIL_TYPE: 'db-email',
        LETTER_TYPE: 'db-letter',
    }

    send_fn = send_fns[template_type]

    send_fn.apply_async(
        (
            str(service.id),
            create_uuid(),
            encrypted,
            datetime.utcnow().strftime(DATETIME_FORMAT)
        ),
        queue=queues[template_type] if not service.research_mode else 'research-mode'
    )


def __sending_limits_for_job_exceeded(service, job, job_id):
    total_sent = fetch_todays_total_message_count(service.id)

    if total_sent + job.notification_count > service.message_limit:
        job.job_status = 'sending limits exceeded'
        job.processing_finished = datetime.utcnow()
        dao_update_job(job)
        current_app.logger.info(
            "Job {} size {} error. Sending limits {} exceeded".format(
                job_id, job.notification_count, service.message_limit)
        )
        return True
    return False


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
        saved_notification = persist_notification(template_id=notification['template'],
                                                  template_version=notification['template_version'],
                                                  recipient=notification['to'],
                                                  service=service,
                                                  personalisation=notification.get('personalisation'),
                                                  notification_type=SMS_TYPE,
                                                  api_key_id=api_key_id,
                                                  key_type=key_type,
                                                  created_at=created_at,
                                                  job_id=notification.get('job', None),
                                                  job_row_number=notification.get('row_number', None),
                                                  notification_id=notification_id
                                                  )

        provider_tasks.deliver_sms.apply_async(
            [str(saved_notification.id)],
            queue='send-sms' if not service.research_mode else 'research-mode'
        )

        current_app.logger.info(
            "SMS {} created at {} for job {}".format(saved_notification.id, created_at, notification.get('job', None))
        )

    except SQLAlchemyError as e:
        handle_exception(self, notification, notification_id, e)


@notify_celery.task(bind=True, name="send-email", max_retries=5, default_retry_delay=300)
@statsd(namespace="tasks")
def send_email(self,
               service_id,
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
        saved_notification = persist_notification(
            template_id=notification['template'],
            template_version=notification['template_version'],
            recipient=notification['to'],
            service=service,
            personalisation=notification.get('personalisation'),
            notification_type=EMAIL_TYPE,
            api_key_id=api_key_id,
            key_type=key_type,
            created_at=created_at,
            job_id=notification.get('job', None),
            job_row_number=notification.get('row_number', None),
            notification_id=notification_id
        )

        provider_tasks.deliver_email.apply_async(
            [str(saved_notification.id)],
            queue='send-email' if not service.research_mode else 'research-mode'
        )

        current_app.logger.info("Email {} created at {}".format(saved_notification.id, created_at))
    except SQLAlchemyError as e:
        handle_exception(self, notification, notification_id, e)


@notify_celery.task(bind=True, name="persist-letter", max_retries=5, default_retry_delay=300)
@statsd(namespace="tasks")
def persist_letter(
    self,
    service_id,
    notification_id,
    encrypted_notification,
    created_at
):
    notification = encryption.decrypt(encrypted_notification)

    # we store the recipient as just the first item of the person's address
    recipient = notification['personalisation']['addressline1']

    service = dao_fetch_service_by_id(service_id)
    try:
        saved_notification = persist_notification(
            template_id=notification['template'],
            template_version=notification['template_version'],
            recipient=recipient,
            service=service,
            personalisation=notification['personalisation'],
            notification_type=LETTER_TYPE,
            api_key_id=None,
            key_type=KEY_TYPE_NORMAL,
            created_at=created_at,
            job_id=notification['job'],
            job_row_number=notification['row_number'],
            notification_id=notification_id
        )

        current_app.logger.info("Letter {} created at {}".format(saved_notification.id, created_at))
    except SQLAlchemyError as e:
        handle_exception(self, notification, notification_id, e)


@notify_celery.task(bind=True, name="build-dvla-file", max_retries=15, default_retry_delay=300)
@statsd(namespace="tasks")
def build_dvla_file(self, job_id):
    if all_notifications_are_created_for_job(job_id):
        notifications = dao_get_all_notifications_for_job(job_id)
        file = ""
        for n in notifications:
            t = {"content": n.template.content, "subject": n.template.subject}
            # This unique id is a 7 digits requested by DVLA, not known if this number needs to be sequential.
            unique_id = int(''.join(map(str, random.sample(range(9), 7))))
            template = LetterDVLATemplate(t, n.personalisation, unique_id)
            file = file + str(template) + "\n"
        s3upload(filedata=file,
                 region=current_app.config['AWS_REGION'],
                 bucket_name=current_app.config['DVLA_UPLOAD_BUCKET_NAME'],
                 file_location="{}-dvla-job.text".format(job_id))
    else:
        self.retry(queue="retry", exc="All notifications for job {} are not persisted".format(job_id))


def s3upload(filedata, region, bucket_name, file_location):
    # TODO: move this method to utils. Will need to change the filedata from here to send contents in filedata['data']
    _s3 = resource('s3')
    # contents = filedata['data']
    contents = filedata

    exists = True
    try:
        _s3.meta.client.head_bucket(
            Bucket=bucket_name)
    except botocore.exceptions.ClientError as e:
        error_code = int(e.response['Error']['Code'])
        if error_code == 404:
            exists = False
        else:
            current_app.logger.error(
                "Unable to create s3 bucket {}".format(bucket_name))
            raise e

    if not exists:
        _s3.create_bucket(Bucket=bucket_name,
                          CreateBucketConfiguration={'LocationConstraint': region})

    upload_id = create_uuid()
    upload_file_name = file_location
    key = _s3.Object(bucket_name, upload_file_name)
    key.put(Body=contents, ServerSideEncryption='AES256')

    return upload_id


def handle_exception(task, notification, notification_id, exc):
    if not get_notification_by_id(notification_id):
        retry_msg = '{task} notification for job {job} row number {row} and notification id {noti}'.format(
            task=task.__name__,
            job=notification.get('job', None),
            row=notification.get('row_number', None),
            noti=notification_id
        )
        # Sometimes, SQS plays the same message twice. We should be able to catch an IntegrityError, but it seems
        # SQLAlchemy is throwing a FlushError. So we check if the notification id already exists then do not
        # send to the retry queue.
        current_app.logger.exception('Retry' + retry_msg)
        try:
            task.retry(queue="retry", exc=exc)
        except task.MaxRetriesExceededError:
            current_app.logger.exception('Retry' + retry_msg)


def get_template_class(template_type):
    if template_type == SMS_TYPE:
        return SMSMessageTemplate
    elif template_type in (EMAIL_TYPE, LETTER_TYPE):
        # since we don't need rendering capabilities (we only need to extract placeholders) both email and letter can
        # use the same base template
        return WithSubjectTemplate
