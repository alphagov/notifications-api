from app import create_uuid, DATETIME_FORMAT, DATE_FORMAT
from app import notify_celery, encryption, firetext_client, aws_ses_client
from app.clients.email.aws_ses import AwsSesClientException
from app.clients.sms.firetext import FiretextClientException
from app.dao.services_dao import dao_fetch_service_by_id
from app.dao.templates_dao import dao_get_template_by_id
from app.dao.notifications_dao import (
    dao_create_notification,
    dao_update_notification,
    delete_failed_notifications_created_more_than_a_week_ago,
    delete_successful_notifications_created_more_than_a_day_ago,
    dao_get_notification_statistics_for_service_and_day,
    update_notification_reference_by_id
)
from app.dao.jobs_dao import dao_update_job, dao_get_job_by_id
from app.dao.users_dao import delete_codes_older_created_more_than_a_day_ago
from app.dao.invited_user_dao import delete_invitations_created_more_than_two_days_ago
from app.models import (
    Notification,
    TEMPLATE_TYPE_EMAIL,
    TEMPLATE_TYPE_SMS
)
from flask import current_app
from sqlalchemy.exc import SQLAlchemyError
from app.aws import s3
from datetime import datetime
from utils.template import Template
from utils.recipients import RecipientCSV, format_phone_number, validate_phone_number
from app.validation import (allowed_send_to_email, allowed_send_to_number)


@notify_celery.task(name="delete-verify-codes")
def delete_verify_codes():
    try:
        start = datetime.utcnow()
        deleted = delete_codes_older_created_more_than_a_day_ago()
        current_app.logger.info(
            "Delete job started {} finished {} deleted {} verify codes".format(start, datetime.utcnow(), deleted)
        )
    except SQLAlchemyError:
        current_app.logger.info("Failed to delete verify codes")
        raise


@notify_celery.task(name="delete-successful-notifications")
def delete_successful_notifications():
    try:
        start = datetime.utcnow()
        deleted = delete_successful_notifications_created_more_than_a_day_ago()
        current_app.logger.info(
            "Delete job started {} finished {} deleted {} successful notifications".format(
                start,
                datetime.utcnow(),
                deleted
            )
        )
    except SQLAlchemyError:
        current_app.logger.info("Failed to delete successful notifications")
        raise


@notify_celery.task(name="delete-failed-notifications")
def delete_failed_notifications():
    try:
        start = datetime.utcnow()
        deleted = delete_failed_notifications_created_more_than_a_week_ago()
        current_app.logger.info(
            "Delete job started {} finished {} deleted {} failed notifications".format(
                start,
                datetime.utcnow(),
                deleted
            )
        )
    except SQLAlchemyError:
        current_app.logger.info("Failed to delete failed notifications")
        raise


@notify_celery.task(name="delete-invitations")
def delete_invitations():
    try:
        start = datetime.utcnow()
        deleted = delete_invitations_created_more_than_two_days_ago()
        current_app.logger.info(
            "Delete job started {} finished {} deleted {} invitations".format(start, datetime.utcnow(), deleted)
        )
    except SQLAlchemyError:
        current_app.logger.info("Failed to delete invitations")
        raise


@notify_celery.task(name="process-job")
def process_job(job_id):
    start = datetime.utcnow()
    job = dao_get_job_by_id(job_id)

    service = job.service

    stats = dao_get_notification_statistics_for_service_and_day(
        service_id=service.id,
        day=job.created_at.strftime(DATE_FORMAT)
    )

    total_sent = 0
    if stats:
        total_sent = stats.emails_requested + stats.sms_requested

    if total_sent + job.notification_count > service.limit:
        job.status = 'sending limits exceeded'
        job.processing_finished = datetime.utcnow()
        dao_update_job(job)
        current_app.logger.info(
            "Job {} size {} error. Sending limits {} exceeded".format(job_id, job.notification_count, service.limit)
        )
        return

    job.status = 'in progress'
    dao_update_job(job)

    template = Template(
        dao_get_template_by_id(job.template_id).__dict__
    )

    for recipient, personalisation in RecipientCSV(
            s3.get_job_from_s3(job.bucket_name, job_id),
            template_type=template.template_type,
            placeholders=template.placeholders
    ).recipients_and_personalisation:

        encrypted = encryption.encrypt({
            'template': template.id,
            'job': str(job.id),
            'to': recipient,
            'personalisation': personalisation
        })

        if template.template_type == 'sms':
            send_sms.apply_async((
                str(job.service_id),
                str(create_uuid()),
                encrypted,
                datetime.utcnow().strftime(DATETIME_FORMAT)),
                queue='bulk-sms'
            )

        if template.template_type == 'email':
            send_email.apply_async((
                str(job.service_id),
                str(create_uuid()),
                template.subject,
                "{}@{}".format(job.service.email_from, current_app.config['NOTIFY_EMAIL_DOMAIN']),
                encrypted,
                datetime.utcnow().strftime(DATETIME_FORMAT)),
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
    service = dao_fetch_service_by_id(service_id)

    client = firetext_client

    try:
        status = 'sent'
        can_send = True

        if not allowed_send_to_number(service, notification['to']):
            current_app.logger.info(
                "SMS {} failed as restricted service".format(notification_id)
            )
            status = 'failed'
            can_send = False

        sent_at = datetime.utcnow()
        notification_db_object = Notification(
            id=notification_id,
            template_id=notification['template'],
            to=notification['to'],
            service_id=service_id,
            job_id=notification.get('job', None),
            status=status,
            created_at=datetime.strptime(created_at, DATETIME_FORMAT),
            sent_at=sent_at,
            sent_by=client.get_name()
        )

        dao_create_notification(notification_db_object, TEMPLATE_TYPE_SMS)

        if can_send:
            try:
                template = Template(
                    dao_get_template_by_id(notification['template']).__dict__,
                    values=notification.get('personalisation', {}),
                    prefix=service.name
                )

                client.send_sms(
                    to=format_phone_number(validate_phone_number(notification['to'])),
                    content=template.replaced,
                    reference=str(notification_id)
                )
            except FiretextClientException as e:
                current_app.logger.error(
                    "SMS notification {} failed".format(notification_id)
                )
                current_app.logger.exception(e)
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
    service = dao_fetch_service_by_id(service_id)

    client = aws_ses_client

    try:
        status = 'sent'
        can_send = True

        if not allowed_send_to_email(service, notification['to']):
            current_app.logger.info(
                "Email {} failed as restricted service".format(notification_id)
            )
            status = 'failed'
            can_send = False

        sent_at = datetime.utcnow()
        notification_db_object = Notification(
            id=notification_id,
            template_id=notification['template'],
            to=notification['to'],
            service_id=service_id,
            job_id=notification.get('job', None),
            status=status,
            created_at=datetime.strptime(created_at, DATETIME_FORMAT),
            sent_at=sent_at,
            sent_by=client.get_name()
        )
        dao_create_notification(notification_db_object, TEMPLATE_TYPE_EMAIL)

        if can_send:
            try:
                template = Template(
                    dao_get_template_by_id(notification['template']).__dict__,
                    values=notification.get('personalisation', {})
                )

                reference = client.send_email(
                    from_address,
                    notification['to'],
                    subject,
                    template.replaced
                )
                update_notification_reference_by_id(notification_id, reference)
            except AwsSesClientException as e:
                current_app.logger.exception(e)
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
        firetext_client.send_sms(
            format_phone_number(validate_phone_number(verification_message['to'])),
            verification_message['secret_code'],
            'send-sms-code'
        )
    except FiretextClientException as e:
        current_app.logger.exception(e)


@notify_celery.task(name='send-email-code')
def send_email_code(encrypted_verification_message):
    verification_message = encryption.decrypt(encrypted_verification_message)
    try:
        aws_ses_client.send_email(current_app.config['VERIFY_CODE_FROM_EMAIL_ADDRESS'],
                                  verification_message['to'],
                                  "Verification code",
                                  verification_message['secret_code'])
    except AwsSesClientException as e:
        current_app.logger.exception(e)


# TODO: when placeholders in templates work, this will be a real template
def invitation_template(user_name, service_name, url, expiry_date):
    from string import Template
    t = Template(
        '$user_name has invited you to collaborate on $service_name on GOV.UK Notify.\n\n'
        'GOV.UK Notify makes it easy to keep people updated by helping you send text messages, emails and letters.\n\n'
        'Click this link to create an account on GOV.UK Notify:\n$url\n\n'
        'This invitation will stop working at midnight tomorrow. This is to keep $service_name secure.')
    return t.substitute(user_name=user_name, service_name=service_name, url=url, expiry_date=expiry_date)


def invitation_subject_line(user_name, service_name):
    from string import Template
    t = Template('$user_name has invited you to collaborate on $service_name on GOV.UK Notify')
    return t.substitute(user_name=user_name, service_name=service_name)


def invited_user_url(base_url, token):
    return '{0}/invitation/{1}'.format(base_url, token)


@notify_celery.task(name='email-invited-user')
def email_invited_user(encrypted_invitation):
    invitation = encryption.decrypt(encrypted_invitation)
    url = invited_user_url(current_app.config['ADMIN_BASE_URL'],
                           invitation['token'])
    invitation_content = invitation_template(invitation['user_name'],
                                             invitation['service_name'],
                                             url,
                                             invitation['expiry_date'])
    try:
        email_from = "{}@{}".format(current_app.config['INVITATION_EMAIL_FROM'],
                                    current_app.config['NOTIFY_EMAIL_DOMAIN'])
        subject_line = invitation_subject_line(invitation['user_name'], invitation['service_name'])
        aws_ses_client.send_email(email_from,
                                  invitation['to'],
                                  subject_line,
                                  invitation_content)
    except AwsSesClientException as e:
        current_app.logger.exception(e)


def password_reset_message(name, url):
    from string import Template
    t = Template("Hi $user_name,\n\n"
                 "We received a request to reset your password on GOV.UK Notify.\n\n"
                 "If you didn't request this email, you can ignore it – your password has not been changed.\n\n"
                 "To reset your password, click this link:\n\n"
                 "$url")
    return t.substitute(user_name=name, url=url)


@notify_celery.task(name='email-reset-password')
def email_reset_password(encrypted_reset_password_message):
    reset_password_message = encryption.decrypt(encrypted_reset_password_message)
    try:
        aws_ses_client.send_email(current_app.config['VERIFY_CODE_FROM_EMAIL_ADDRESS'],
                                  reset_password_message['to'],
                                  "Reset your GOV.UK Notify password",
                                  password_reset_message(name=reset_password_message['name'],
                                                         url=reset_password_message['reset_password_url']))
    except AwsSesClientException as e:
        current_app.logger.exception(e)
