from urllib import parse
from datetime import datetime

from flask import current_app
from notifications_utils.recipients import (
    validate_and_format_phone_number
)
from notifications_utils.template import HTMLEmailTemplate, PlainTextEmailTemplate, SMSMessageTemplate

from app import clients, statsd_client, create_uuid
from app.dao.notifications_dao import dao_update_notification
from app.dao.provider_details_dao import (
    get_provider_details_by_notification_type,
    dao_toggle_sms_provider
)
from app.celery.research_mode_tasks import send_sms_response, send_email_response
from app.dao.templates_dao import dao_get_template_by_id
from app.models import SMS_TYPE, KEY_TYPE_TEST, BRANDING_ORG, EMAIL_TYPE, NOTIFICATION_TECHNICAL_FAILURE


def send_sms_to_provider(notification):
    service = notification.service
    if service_is_inactive(service, notification):
        return

    if notification.status == 'created':
        provider = provider_to_use(SMS_TYPE, notification.id)
        current_app.logger.info(
            "Starting sending SMS {} to provider at {}".format(notification.id, datetime.utcnow())
        )
        template_model = dao_get_template_by_id(notification.template_id, notification.template_version)
        template = SMSMessageTemplate(
            template_model.__dict__,
            values=notification.personalisation,
            prefix=service.name,
            sender=service.sms_sender
        )

        if service.research_mode or notification.key_type == KEY_TYPE_TEST:
            notification.billable_units = 0
            update_notification(notification, provider)
            send_sms_response(provider.get_name(), str(notification.id), notification.to)
        else:
            try:
                provider.send_sms(
                    to=validate_and_format_phone_number(notification.to),
                    content=str(template),
                    reference=str(notification.id),
                    sender=service.sms_sender
                )
            except Exception as e:
                dao_toggle_sms_provider(provider.name)
                raise e
            else:
                notification.billable_units = template.fragment_count
                update_notification(notification, provider)

        current_app.logger.info(
            "SMS {} sent to provider {} at {}".format(notification.id, provider.get_name(), notification.sent_at)
        )
        delta_milliseconds = (datetime.utcnow() - notification.created_at).total_seconds() * 1000
        statsd_client.timing("sms.total-time", delta_milliseconds)


def send_email_to_provider(notification):
    service = notification.service
    if service_is_inactive(service, notification):
        return
    if notification.status == 'created':
        provider = provider_to_use(EMAIL_TYPE, notification.id)
        current_app.logger.info(
            "Starting sending EMAIL {} to provider at {}".format(notification.id, datetime.utcnow())
        )
        template_dict = dao_get_template_by_id(notification.template_id, notification.template_version).__dict__

        html_email = HTMLEmailTemplate(
            template_dict,
            values=notification.personalisation,
            **get_html_email_options(service)
        )

        plain_text_email = PlainTextEmailTemplate(
            template_dict,
            values=notification.personalisation
        )

        if service.research_mode or notification.key_type == KEY_TYPE_TEST:
            reference = str(create_uuid())
            notification.billable_units = 0
            notification.reference = reference
            update_notification(notification, provider)
            send_email_response(provider.get_name(), reference, notification.to)
        else:
            from_address = '"{}" <{}@{}>'.format(service.name, service.email_from,
                                                 current_app.config['NOTIFY_EMAIL_DOMAIN'])
            reference = provider.send_email(
                from_address,
                notification.to,
                plain_text_email.subject,
                body=str(plain_text_email),
                html_body=str(html_email),
                reply_to_address=service.reply_to_email_address,
            )
            notification.reference = reference
            update_notification(notification, provider)

        current_app.logger.info(
            "Email {} sent to provider at {}".format(notification.id, notification.sent_at)
        )
        delta_milliseconds = (datetime.utcnow() - notification.created_at).total_seconds() * 1000
        statsd_client.timing("email.total-time", delta_milliseconds)


def update_notification(notification, provider):
    notification.sent_at = datetime.utcnow()
    notification.sent_by = provider.get_name()
    notification.status = 'sending'
    dao_update_notification(notification)


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


def get_logo_url(base_url, branding_path, logo_file):
    """
    Get the complete URL for a given logo.

    We have to convert the base_url into a static url. Our hosted environments all have their own cloudfront instances,
    found at the static subdomain (eg https://static.notifications.service.gov.uk).

    If running locally (dev environment), don't try and use cloudfront - just stick to the actual underlying source
    ({URL}/static/{PATH})
    """
    base_url = parse.urlparse(base_url)
    netloc = base_url.netloc

    if (
        base_url.netloc.startswith('localhost') or
        # covers both preview and staging
        'notify.works' in base_url.netloc
    ):
        path = '/static' + branding_path + logo_file
    else:
        if base_url.netloc.startswith('www'):
            # strip "www."
            netloc = base_url.netloc[4:]

        netloc = 'static.' + netloc
        path = branding_path + logo_file

    logo_url = parse.ParseResult(
        scheme=base_url.scheme,
        netloc=netloc,
        path=path,
        params=base_url.params,
        query=base_url.query,
        fragment=base_url.fragment
    )
    return parse.urlunparse(logo_url)


def get_html_email_options(service):
    govuk_banner = service.branding != BRANDING_ORG
    if service.organisation:
        logo_url = get_logo_url(
            current_app.config['ADMIN_BASE_URL'],
            current_app.config['BRANDING_PATH'],
            service.organisation.logo
        )

        branding = {
            'brand_colour': service.organisation.colour,
            'brand_logo': logo_url,
            'brand_name': service.organisation.name,
        }
    else:
        branding = {}

    return dict(govuk_banner=govuk_banner, **branding)


def service_is_inactive(service, notification):
    """
    If service is inactive update the notification to technical failure and return true.
    :param service:
    :param notification:
    :return:
    """
    if not service.active:
        notification.status = NOTIFICATION_TECHNICAL_FAILURE
        dao_update_notification(notification)
        current_app.logger.warn(
            "Send {} for notification id {} to provider is not allowed: service {} is inactive".format(
                notification.notification_type,
                notification.id,
                service.id))
    return not service.active
