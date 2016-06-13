import itertools
from datetime import (datetime, timedelta)

from flask import current_app
from monotonic import monotonic
from sqlalchemy.exc import SQLAlchemyError
from app import clients, statsd_client
from app.clients import STATISTICS_FAILURE
from app.clients.email import EmailClientException
from app.clients.sms import SmsClientException
from app.dao.services_dao import dao_fetch_service_by_id
from app.dao.templates_dao import dao_get_template_by_id
from app.dao.provider_details_dao import get_provider_details_by_notification_type
from app.celery.research_mode_tasks import send_email_response, send_sms_response

from notifications_utils.template import Template, unlink_govuk_escaped

from notifications_utils.recipients import (
    RecipientCSV,
    validate_and_format_phone_number,
    allowed_to_send_to
)

from app import (
    create_uuid,
    DATETIME_FORMAT,
    DATE_FORMAT,
    notify_celery,
    encryption
)

from app.aws import s3
from app.dao.users_dao import delete_codes_older_created_more_than_a_day_ago
from app.dao.invited_user_dao import delete_invitations_created_more_than_two_days_ago

from app.dao.notifications_dao import (
    dao_create_notification,
    dao_update_notification,
    delete_notifications_created_more_than_a_week_ago,
    dao_get_notification_statistics_for_service_and_day,
    update_provider_stats,
    get_notifications,
    update_notification_status_by_id
)

from app.dao.jobs_dao import (
    dao_update_job,
    dao_get_job_by_id
)

from app.models import (
    Notification,
    TEMPLATE_TYPE_EMAIL,
    TEMPLATE_TYPE_SMS
)


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
        deleted = delete_notifications_created_more_than_a_week_ago('delivered')
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
        deleted = delete_notifications_created_more_than_a_week_ago('failed')
        deleted += delete_notifications_created_more_than_a_week_ago('technical-failure')
        deleted += delete_notifications_created_more_than_a_week_ago('temporary-failure')
        deleted += delete_notifications_created_more_than_a_week_ago('permanent-failure')
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
    task_start = monotonic()
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

        if template.template_type == 'sms':
            send_sms.apply_async((
                str(job.service_id),
                create_uuid(),
                encrypted,
                datetime.utcnow().strftime(DATETIME_FORMAT)),
                queue='bulk-sms'
            )

        if template.template_type == 'email':
            from_email = '"{}" <{}@{}>'.format(
                service.name,
                service.email_from,
                current_app.config['NOTIFY_EMAIL_DOMAIN']
            )

            send_email.apply_async((
                str(job.service_id),
                create_uuid(),
                from_email.encode('ascii', 'ignore').decode('ascii'),
                encrypted,
                datetime.utcnow().strftime(DATETIME_FORMAT)),
                {'reply_to_addresses': service.reply_to_email_address},
                queue='bulk-email')

    finished = datetime.utcnow()
    job.status = 'finished'
    job.processing_started = start
    job.processing_finished = finished
    dao_update_job(job)
    remove_job.apply_async((str(job_id),), queue='remove-job')
    current_app.logger.info(
        "Job {} created at {} started at {} finished at {}".format(job_id, job.created_at, start, finished)
    )
    statsd_client.incr("notifications.tasks.process-job")
    statsd_client.timing("notifications.tasks.process-job.task-time", monotonic() - task_start)


@notify_celery.task(name="remove-job")
def remove_job(job_id):
    job = dao_get_job_by_id(job_id)
    s3.remove_job_from_s3(job.service.id, str(job_id))
    current_app.logger.info("Job {} has been removed from s3.".format(job_id))


@notify_celery.task(name="send-sms")
def send_sms(service_id, notification_id, encrypted_notification, created_at):
    task_start = monotonic()
    notification = encryption.decrypt(encrypted_notification)
    service = dao_fetch_service_by_id(service_id)

    provider = provider_to_use('sms', notification_id)

    if not service_allowed_to_send_to(notification['to'], service):
        current_app.logger.info(
            "SMS {} failed as restricted service".format(notification_id)
        )
        return

    try:

        template = Template(
            dao_get_template_by_id(notification['template'], notification['template_version']).__dict__,
            values=notification.get('personalisation', {}),
            prefix=service.name
        )

        sent_at = datetime.utcnow()
        notification_db_object = Notification(
            id=notification_id,
            template_id=notification['template'],
            template_version=notification['template_version'],
            to=notification['to'],
            service_id=service_id,
            job_id=notification.get('job', None),
            job_row_number=notification.get('row_number', None),
            status='sending',
            created_at=datetime.strptime(created_at, DATETIME_FORMAT),
            sent_at=sent_at,
            sent_by=provider.get_name(),
            content_char_count=template.replaced_content_count
        )
        statsd_client.timing_with_dates(
            "notifications.tasks.send-sms.queued-for",
            sent_at,
            datetime.strptime(created_at, DATETIME_FORMAT)
        )
        dao_create_notification(notification_db_object, TEMPLATE_TYPE_SMS, provider.get_name())

        try:
            if service.research_mode:
                send_sms_response.apply_async(
                    (provider.get_name(), str(notification_id), notification['to']), queue='research-mode'
                )
            else:
                provider.send_sms(
                    to=validate_and_format_phone_number(notification['to']),
                    content=template.replaced,
                    reference=str(notification_id)
                )

                update_provider_stats(
                    notification_id,
                    'sms',
                    provider.get_name()
                )

        except SmsClientException as e:
            current_app.logger.error(
                "SMS notification {} failed".format(notification_id)
            )
            current_app.logger.exception(e)
            notification_db_object.status = 'technical-failure'
            dao_update_notification(notification_db_object)

        current_app.logger.info(
            "SMS {} created at {} sent at {}".format(notification_id, created_at, sent_at)
        )
        statsd_client.incr("notifications.tasks.send-sms")
        statsd_client.timing("notifications.tasks.send-sms.task-time", monotonic() - task_start)
    except SQLAlchemyError as e:
        current_app.logger.exception(e)


@notify_celery.task(name="send-email")
def send_email(service_id, notification_id, from_address, encrypted_notification, created_at, reply_to_addresses=None):
    task_start = monotonic()
    notification = encryption.decrypt(encrypted_notification)
    service = dao_fetch_service_by_id(service_id)

    provider = provider_to_use('email', notification_id)

    if not service_allowed_to_send_to(notification['to'], service):
        current_app.logger.info(
            "Email {} failed as restricted service".format(notification_id)
        )
        return

    try:
        sent_at = datetime.utcnow()
        notification_db_object = Notification(
            id=notification_id,
            template_id=notification['template'],
            template_version=notification['template_version'],
            to=notification['to'],
            service_id=service_id,
            job_id=notification.get('job', None),
            job_row_number=notification.get('row_number', None),
            status='sending',
            created_at=datetime.strptime(created_at, DATETIME_FORMAT),
            sent_at=sent_at,
            sent_by=provider.get_name()
        )

        dao_create_notification(notification_db_object, TEMPLATE_TYPE_EMAIL, provider.get_name())
        statsd_client.timing_with_dates(
            "notifications.tasks.send-email.queued-for",
            sent_at,
            datetime.strptime(created_at, DATETIME_FORMAT)
        )

        try:
            template = Template(
                dao_get_template_by_id(notification['template'], notification['template_version']).__dict__,
                values=notification.get('personalisation', {})
            )

            if service.research_mode:
                reference = create_uuid()
                send_email_response.apply_async(
                    (provider.get_name(), str(reference), notification['to']), queue='research-mode'
                )
            else:
                reference = provider.send_email(
                    from_address,
                    notification['to'],
                    template.replaced_subject,
                    body=template.replaced_govuk_escaped,
                    html_body=template.as_HTML_email,
                    reply_to_addresses=reply_to_addresses,
                )

                update_provider_stats(
                    notification_id,
                    'email',
                    provider.get_name()
                )

            notification_db_object.reference = reference
            dao_update_notification(notification_db_object)

        except EmailClientException as e:
            current_app.logger.exception(e)
            notification_db_object.status = 'technical-failure'
            dao_update_notification(notification_db_object)

        current_app.logger.info(
            "Email {} created at {} sent at {}".format(notification_id, created_at, sent_at)
        )
        statsd_client.incr("notifications.tasks.send-email")
        statsd_client.timing("notifications.tasks.send-email.task-time", monotonic() - task_start)
    except SQLAlchemyError as e:
        current_app.logger.exception(e)


# TODO: when placeholders in templates work, this will be a real template
def invitation_template(user_name, service_name, url, expiry_date):
    from string import Template
    t = Template(
        '$user_name has invited you to collaborate on $service_name on GOV.UK Notify.\n\n'
        'GOV.UK Notify makes it easy to keep people updated by helping you send text messages, emails and letters.\n\n'
        'Click this link to create an account on GOV.UK Notify:\n$url\n\n'
        'This invitation will stop working at midnight tomorrow. This is to keep $service_name secure.')
    return unlink_govuk_escaped(
        t.substitute(user_name=user_name, service_name=service_name, url=url, expiry_date=expiry_date)
    )


def invitation_subject_line(user_name, service_name):
    from string import Template
    t = Template('$user_name has invited you to collaborate on $service_name on GOV.UK Notify')
    return unlink_govuk_escaped(
        t.substitute(user_name=user_name, service_name=service_name)
    )


def invited_user_url(base_url, token):
    return '{0}/invitation/{1}'.format(base_url, token)


@notify_celery.task(name='email-invited-user')
def email_invited_user(encrypted_invitation):
    provider = provider_to_use('email', 'email-invited-user')

    invitation = encryption.decrypt(encrypted_invitation)
    url = invited_user_url(current_app.config['ADMIN_BASE_URL'],
                           invitation['token'])
    invitation_content = invitation_template(invitation['user_name'],
                                             invitation['service_name'],
                                             url,
                                             invitation['expiry_date'])
    try:
        email_from = '"GOV.UK Notify" <{}@{}>'.format(
            current_app.config['INVITATION_EMAIL_FROM'],
            current_app.config['NOTIFY_EMAIL_DOMAIN']
        )
        subject_line = invitation_subject_line(invitation['user_name'], invitation['service_name'])
        provider.send_email(email_from,
                            invitation['to'],
                            subject_line,
                            invitation_content)
    except EmailClientException as e:
        current_app.logger.exception(e)


def password_reset_message(name, url):
    from string import Template
    t = Template("Hi $user_name,\n\n"
                 "We received a request to reset your password on GOV.UK Notify.\n\n"
                 "If you didn't request this email, you can ignore it – your password has not been changed.\n\n"
                 "To reset your password, click this link:\n\n"
                 "$url")
    return unlink_govuk_escaped(
        t.substitute(user_name=name, url=url)
    )


@notify_celery.task(name='email-reset-password')
def email_reset_password(encrypted_reset_password_message):
    provider = provider_to_use('email', 'email-reset-password')

    reset_password_message = encryption.decrypt(encrypted_reset_password_message)
    try:
        email_from = '"GOV.UK Notify" <{}>'.format(
            current_app.config['VERIFY_CODE_FROM_EMAIL_ADDRESS']
        )
        provider.send_email(
            email_from,
            reset_password_message['to'],
            "Reset your GOV.UK Notify password",
            password_reset_message(
                name=reset_password_message['name'],
                url=reset_password_message['reset_password_url']
            )
        )
    except EmailClientException as e:
        current_app.logger.exception(e)


def registration_verification_template(name, url):
    from string import Template
    t = Template("Hi $name,\n\n"
                 "To complete your registration for GOV.UK Notify please click the link below\n\n $url")
    return unlink_govuk_escaped(
        t.substitute(name=name, url=url)
    )


@notify_celery.task(name='email-registration-verification')
def email_registration_verification(encrypted_verification_message):
    provider = provider_to_use('email', 'email-reset-password')

    verification_message = encryption.decrypt(encrypted_verification_message)
    try:
        email_from = '"GOV.UK Notify" <{}>'.format(
            current_app.config['VERIFY_CODE_FROM_EMAIL_ADDRESS']
        )
        provider.send_email(
            email_from,
            verification_message['to'],
            "Confirm GOV.UK Notify registration",
            registration_verification_template(
                name=verification_message['name'],
                url=verification_message['url'])
        )
    except EmailClientException as e:
        current_app.logger.exception(e)


def service_allowed_to_send_to(recipient, service):
    if not service.restricted:
        return True

    return allowed_to_send_to(
        recipient,
        itertools.chain.from_iterable(
            [user.mobile_number, user.email_address] for user in service.users
        )
    )


def provider_to_use(notification_type, notification_id):
    active_providers_in_order = [
        provider for provider in get_provider_details_by_notification_type(notification_type) if provider.active
        ]

    if not active_providers_in_order:
        current_app.logger.error(
            "{} {} failed as no active providers".format(notification_type, notification_id)
        )
        raise Exception("No active {} providers".format(notification_type))

    return clients.get_client_by_name_and_type(active_providers_in_order[0].identifier, notification_type)


@notify_celery.task(name='timeout-sending-notifications')
def timeout_notifications():
    notifications = get_notifications(filter_dict={'status': 'sending'})
    now = datetime.utcnow()
    for noti in notifications:
        try:
            if (now - noti.created_at) > timedelta(
                seconds=current_app.config.get('SENDING_NOTIFICATIONS_TIMEOUT_PERIOD')
            ):
                update_notification_status_by_id(noti.id, 'temporary-failure', STATISTICS_FAILURE)
                current_app.logger.info((
                    "Timeout period reached for notification ({})"
                    ", status has been updated.").format(noti.id))
        except Exception as e:
            current_app.logger.exception(e)
            current_app.logger.error((
                "Exception raised trying to timeout notification ({})"
                ", skipping notification update.").format(noti.id))
