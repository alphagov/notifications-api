from app import create_uuid
from app import notify_celery, encryption, firetext_client, aws_ses_client
from app.clients.email.aws_ses import AwsSesClientException
from app.clients.sms.firetext import FiretextClientException
from app.dao.templates_dao import dao_get_template_by_id
from app.dao.notifications_dao import dao_create_notification, dao_update_notification
from app.dao.jobs_dao import dao_update_job, dao_get_job_by_id
from app.models import Notification
from flask import current_app
from sqlalchemy.exc import SQLAlchemyError
from app.aws import s3
from datetime import datetime
from utils.process_csv import get_recipients_from_csv


@notify_celery.task(name="process-job")
def process_job(job_id):
    start = datetime.utcnow()
    job = dao_get_job_by_id(job_id)
    job.status = 'in progress'
    dao_update_job(job)

    for recipient in get_recipients_from_csv(
        s3.get_job_from_s3(job.bucket_name, job_id),
        template_type=job.template.template_type
    ):
        encrypted = encryption.encrypt({
            'template': job.template_id,
            'job': str(job.id),
            'to': recipient
        })

        if job.template.template_type == 'sms':
            send_sms.apply_async((
                str(job.service_id),
                str(create_uuid()),
                encrypted,
                str(datetime.utcnow())),
                queue='bulk-sms'
            )

        if job.template.template_type == 'email':
            send_email.apply_async((
                str(job.service_id),
                str(create_uuid()),
                job.template.subject,
                "{}@{}".format(job.service.email_from, current_app.config['NOTIFY_EMAIL_DOMAIN']),
                encrypted,
                str(datetime.utcnow())),
                queue='bulk-email')

    finished = datetime.utcnow()
    job.status = 'finished'
    job.processing_started = start
    job.processing_finished = finished
    dao_update_job(job)
    current_app.logger.info(
        "Job {} created at {} started at {} finished at {}".format(job_id, job.created_at, start, finished)
    )


@notify_celery.task(name="send-sms")
def send_sms(service_id, notification_id, encrypted_notification, created_at):
    notification = encryption.decrypt(encrypted_notification)
    template = dao_get_template_by_id(notification['template'])

    client = firetext_client

    try:
        sent_at = datetime.utcnow()
        notification_db_object = Notification(
            id=notification_id,
            template_id=notification['template'],
            to=notification['to'],
            service_id=service_id,
            job_id=notification.get('job', None),
            status='sent',
            created_at=created_at,
            sent_at=sent_at,
            sent_by=client.get_name()

        )
        dao_create_notification(notification_db_object)

        try:
            client.send_sms(notification['to'], template.content)
        except FiretextClientException as e:
            current_app.logger.debug(e)
            notification_db_object.status = 'failed'
            dao_update_notification(notification_db_object)

        current_app.logger.info(
            "SMS {} created at {} sent at {}".format(notification_id, created_at, sent_at)
        )
    except SQLAlchemyError as e:
        current_app.logger.debug(e)


@notify_celery.task(name="send-email")
def send_email(service_id, notification_id, subject, from_address, encrypted_notification, created_at):
    notification = encryption.decrypt(encrypted_notification)
    template = dao_get_template_by_id(notification['template'])

    client = aws_ses_client

    try:
        sent_at = datetime.utcnow()
        notification_db_object = Notification(
            id=notification_id,
            template_id=notification['template'],
            to=notification['to'],
            service_id=service_id,
            job_id=notification.get('job', None),
            status='sent',
            created_at=created_at,
            sent_at=sent_at,
            sent_by=client.get_name()
        )
        dao_create_notification(notification_db_object)

        try:
            client.send_email(
                from_address,
                notification['to'],
                subject,
                template.content
            )
        except AwsSesClientException as e:
            current_app.logger.debug(e)
            notification_db_object.status = 'failed'
            dao_update_notification(notification_db_object)

        current_app.logger.info(
            "Email {} created at {} sent at {}".format(notification_id, created_at, sent_at)
        )
    except SQLAlchemyError as e:
        current_app.logger.debug(e)


@notify_celery.task(name='send-sms-code')
def send_sms_code(encrypted_verification):
    verification_message = encryption.decrypt(encrypted_verification)
    try:
        firetext_client.send_sms(verification_message['to'], verification_message['secret_code'])
    except FiretextClientException as e:
        current_app.logger.error(e)


@notify_celery.task(name='send-email-code')
def send_email_code(encrypted_verification_message):
    verification_message = encryption.decrypt(encrypted_verification_message)
    try:
        aws_ses_client.send_email(current_app.config['VERIFY_CODE_FROM_EMAIL_ADDRESS'],
                                  verification_message['to'],
                                  "Verification code",
                                  verification_message['secret_code'])
    except AwsSesClientException as e:
        current_app.logger.error(e)
