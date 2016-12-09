from datetime import datetime

from flask import current_app
from notifications_utils.recipients import (
    validate_and_format_phone_number
)
from notifications_utils.template import HTMLEmailTemplate, PlainTextEmailTemplate, SMSMessageTemplate

from app import clients, statsd_client, create_uuid
from app.dao.notifications_dao import dao_update_notification
from app.dao.provider_details_dao import get_provider_details_by_notification_type
from app.dao.services_dao import dao_fetch_service_by_id
from app.celery.research_mode_tasks import send_sms_response, send_email_response
from app.dao.templates_dao import dao_get_template_by_id

from app.models import SMS_TYPE, KEY_TYPE_TEST, BRANDING_ORG, EMAIL_TYPE


def send_sms_to_provider(notification):
    service = dao_fetch_service_by_id(notification.service_id)
    provider = provider_to_use(SMS_TYPE, notification.id)
    if notification.status == 'created':
        template_model = dao_get_template_by_id(notification.template_id, notification.template_version)
        template = SMSMessageTemplate(
            template_model.__dict__,
            values=notification.personalisation,
            prefix=service.name,
            sender=service.sms_sender
        )
        if service.research_mode or notification.key_type == KEY_TYPE_TEST:
            send_sms_response.apply_async(
                (provider.get_name(), str(notification.id), notification.to), queue='research-mode'
            )
            notification.billable_units = 0
        else:
            provider.send_sms(
                to=validate_and_format_phone_number(notification.to),
                content=str(template),
                reference=str(notification.id),
                sender=service.sms_sender
            )
            notification.billable_units = template.fragment_count

        notification.sent_at = datetime.utcnow()
        notification.sent_by = provider.get_name()
        notification.status = 'sending'
        dao_update_notification(notification)

        current_app.logger.info(
            "SMS {} sent to provider at {}".format(notification.id, notification.sent_at)
        )
        delta_milliseconds = (datetime.utcnow() - notification.created_at).total_seconds() * 1000
        statsd_client.timing("sms.total-time", delta_milliseconds)


def send_email_to_provider(notification):
    service = dao_fetch_service_by_id(notification.service_id)
    provider = provider_to_use(EMAIL_TYPE, notification.id)
    if notification.status == 'created':
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
            send_email_response.apply_async(
                (provider.get_name(), reference, notification.to), queue='research-mode'
            )
            notification.billable_units = 0
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
        notification.sent_at = datetime.utcnow()
        notification.sent_by = provider.get_name(),
        notification.status = 'sending'
        dao_update_notification(notification)

        current_app.logger.info(
            "Email {} sent to provider at {}".format(notification.id, notification.sent_at)
        )
        delta_milliseconds = (datetime.utcnow() - notification.created_at).total_seconds() * 1000
        statsd_client.timing("email.total-time", delta_milliseconds)


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


def get_html_email_options(service):
    govuk_banner = service.branding != BRANDING_ORG
    if service.organisation:
        logo = '{}{}{}'.format(
            current_app.config['ADMIN_BASE_URL'],
            current_app.config['BRANDING_PATH'],
            service.organisation.logo
        )
        branding = {
            'brand_colour': service.organisation.colour,
            'brand_logo': logo,
            'brand_name': service.organisation.name,
        }
    else:
        branding = {}

    return dict(govuk_banner=govuk_banner, **branding)
