from app import notify_celery, encryption, firetext_client, aws_ses_client
from app.clients.email.aws_ses import AwsSesClientException
from app.clients.sms.firetext import FiretextClientException
from app.dao.templates_dao import get_model_templates
from app.dao.notifications_dao import save_notification
from app.models import Notification
from flask import current_app
from sqlalchemy.exc import SQLAlchemyError


@notify_celery.task(name="send-sms")
def send_sms(service_id, notification_id, encrypted_notification, job_id=None):
    notification = encryption.decrypt(encrypted_notification)
    template = get_model_templates(notification['template'])

    try:
        notification_db_object = Notification(
            id=notification_id,
            template_id=notification['template'],
            to=notification['to'],
            service_id=service_id,
            job_id=job_id,
            status='sent'
        )
        save_notification(notification_db_object)

        try:
            firetext_client.send_sms(notification['to'], template.content)
        except FiretextClientException as e:
            current_app.logger.debug(e)
            save_notification(notification_db_object, {"status": "failed"})

    except SQLAlchemyError as e:
        current_app.logger.debug(e)


@notify_celery.task(name="send-email")
def send_email(service_id, notification_id, subject, from_address, encrypted_notification):
    notification = encryption.decrypt(encrypted_notification)
    template = get_model_templates(notification['template'])

    try:
        notification_db_object = Notification(
            id=notification_id,
            template_id=notification['template'],
            to=notification['to'],
            service_id=service_id,
            status='sent'
        )
        save_notification(notification_db_object)

        try:
            aws_ses_client.send_email(
                from_address,
                notification['to'],
                subject,
                template.content
            )
        except AwsSesClientException as e:
            current_app.logger.debug(e)
            save_notification(notification_db_object, {"status": "failed"})

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
