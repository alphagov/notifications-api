from urllib import parse
from datetime import datetime

from flask import current_app
from notifications_utils.recipients import (
    validate_and_format_phone_number,
    validate_and_format_email_address
)
from notifications_utils.template import HTMLEmailTemplate, PlainTextEmailTemplate, SMSMessageTemplate
from requests.exceptions import HTTPError

from app import clients, statsd_client, create_uuid
from app.dao.notifications_dao import (
    dao_update_notification
)
from app.dao.provider_details_dao import (
    get_provider_details_by_notification_type,
    dao_toggle_sms_provider
)
from app.celery.research_mode_tasks import send_sms_response, send_email_response
from app.dao.templates_dao import dao_get_template_by_id
from app.exceptions import NotificationTechnicalFailureException
from app.models import (
    SMS_TYPE,
    KEY_TYPE_TEST,
    BRANDING_BOTH,
    BRANDING_ORG_BANNER,
    EMAIL_TYPE,
    NOTIFICATION_CREATED,
    NOTIFICATION_TECHNICAL_FAILURE,
    NOTIFICATION_SENT,
    NOTIFICATION_SENDING
)


def send_sms_to_provider(notification):
    service = notification.service

    if not service.active:
        technical_failure(notification=notification)
        return

    if notification.status == 'created':
        provider = provider_to_use(SMS_TYPE, notification.id, notification.international)
        current_app.logger.debug(
            "Starting sending SMS {} to provider at {}".format(notification.id, datetime.utcnow())
        )
        template_model = dao_get_template_by_id(notification.template_id, notification.template_version)

        template = SMSMessageTemplate(
            template_model.__dict__,
            values=notification.personalisation,
            prefix=service.name,
            show_prefix=service.prefix_sms,
        )

        if service.research_mode or notification.key_type == KEY_TYPE_TEST:
            send_sms_response(provider.get_name(), str(notification.id), notification.to)
            update_notification_to_sending(notification, provider)

        else:
            try:
                provider.send_sms(
                    to=validate_and_format_phone_number(notification.to, international=notification.international),
                    content=str(template),
                    reference=str(notification.id),
                    sender=notification.reply_to_text
                )
            except Exception as e:
                notification.billable_units = template.fragment_count
                notification.sent_by = provider.get_name()
                dao_update_notification(notification)
                dao_toggle_sms_provider(provider.name)
                raise e
            else:
                notification.billable_units = template.fragment_count
                update_notification_to_sending(notification, provider)

        current_app.logger.debug(
            "SMS {} sent to provider {} at {}".format(notification.id, provider.get_name(), notification.sent_at)
        )
        delta_milliseconds = (datetime.utcnow() - notification.created_at).total_seconds() * 1000
        statsd_client.timing("sms.total-time", delta_milliseconds)


def send_email_to_provider(notification):
    service = notification.service
    if not service.active:
        technical_failure(notification=notification)
        return
    if notification.status == 'created':
        provider = provider_to_use(EMAIL_TYPE, notification.id)

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
            notification.reference = str(create_uuid())
            update_notification_to_sending(notification, provider)
            send_email_response(notification.reference, notification.to)
        else:
            from_address = '"{}" <{}@{}>'.format(service.name, service.email_from,
                                                 current_app.config['NOTIFY_EMAIL_DOMAIN'])

            email_reply_to = notification.reply_to_text

            reference = provider.send_email(
                from_address,
                validate_and_format_email_address(notification.to),
                plain_text_email.subject,
                body=str(plain_text_email),
                html_body=str(html_email),
                reply_to_address=validate_and_format_email_address(email_reply_to) if email_reply_to else None,
            )
            notification.reference = reference
            update_notification_to_sending(notification, provider)

        current_app.logger.debug(
            "Email {} sent to provider at {}".format(notification.id, notification.sent_at)
        )
        delta_milliseconds = (datetime.utcnow() - notification.created_at).total_seconds() * 1000
        statsd_client.timing("email.total-time", delta_milliseconds)


def update_notification_to_sending(notification, provider):
    notification.sent_at = datetime.utcnow()
    notification.sent_by = provider.get_name()
    notification.status = NOTIFICATION_SENT if notification.international else NOTIFICATION_SENDING
    dao_update_notification(notification)


def provider_to_use(notification_type, notification_id, international=False):
    active_providers_in_order = [
        p for p in get_provider_details_by_notification_type(notification_type, international) if p.active
    ]

    if not active_providers_in_order:
        current_app.logger.error(
            "{} {} failed as no active providers".format(notification_type, notification_id)
        )
        raise Exception("No active {} providers".format(notification_type))

    return clients.get_client_by_name_and_type(active_providers_in_order[0].identifier, notification_type)


def get_logo_url(base_url, logo_file):
    base_url = parse.urlparse(base_url)
    netloc = base_url.netloc

    if base_url.netloc.startswith('localhost'):
        netloc = 'notify.tools'
    elif base_url.netloc.startswith('www'):
        # strip "www."
        netloc = base_url.netloc[4:]

    logo_url = parse.ParseResult(
        scheme=base_url.scheme,
        netloc='static-logos.' + netloc,
        path=logo_file,
        params=base_url.params,
        query=base_url.query,
        fragment=base_url.fragment
    )
    return parse.urlunparse(logo_url)


def get_html_email_options(service):

    if service.email_branding is None:
        return {
            'govuk_banner': True,
            'brand_banner': False,
        }

    logo_url = get_logo_url(
        current_app.config['ADMIN_BASE_URL'],
        service.email_branding.logo
    ) if service.email_branding.logo else None

    return {
        'govuk_banner': service.email_branding.brand_type == BRANDING_BOTH,
        'brand_banner': service.email_branding.brand_type == BRANDING_ORG_BANNER,
        'brand_colour': service.email_branding.colour,
        'brand_logo': logo_url,
        'brand_name': service.email_branding.text,
    }


def technical_failure(notification):
    notification.status = NOTIFICATION_TECHNICAL_FAILURE
    dao_update_notification(notification)
    raise NotificationTechnicalFailureException(
        "Send {} for notification id {} to provider is not allowed: service {} is inactive".format(
            notification.notification_type,
            notification.id,
            notification.service_id))
