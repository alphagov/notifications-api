import random
from urllib import parse
from datetime import datetime, timedelta
from cachetools import TTLCache, cached
from flask import current_app
from notifications_utils.template import HTMLEmailTemplate, PlainTextEmailTemplate, SMSMessageTemplate

from app import notification_provider_clients, statsd_client, create_uuid
from app.dao.email_branding_dao import dao_get_email_branding_by_id
from app.dao.notifications_dao import (
    dao_update_notification
)
from app.dao.provider_details_dao import (
    get_provider_details_by_notification_type,
    dao_reduce_sms_provider_priority
)
from app.celery.research_mode_tasks import send_sms_response, send_email_response
from app.exceptions import NotificationTechnicalFailureException
from app.models import (
    SMS_TYPE,
    KEY_TYPE_TEST,
    BRANDING_BOTH,
    BRANDING_ORG_BANNER,
    EMAIL_TYPE,
    NOTIFICATION_TECHNICAL_FAILURE,
    NOTIFICATION_SENT,
    NOTIFICATION_SENDING,
    NOTIFICATION_STATUS_TYPES_COMPLETED
)
from app.serialised_models import SerialisedTemplate, SerialisedService


def send_sms_to_provider(notification):
    service = SerialisedService.from_id(notification.service_id)

    if not service.active:
        technical_failure(notification=notification)
        return

    if notification.status == 'created':
        provider = provider_to_use(SMS_TYPE, notification.international)

        template_model = SerialisedTemplate.from_id_and_service_id(
            template_id=notification.template_id, service_id=service.id, version=notification.template_version
        )

        template = SMSMessageTemplate(
            template_model.__dict__,
            values=notification.personalisation,
            prefix=service.name,
            show_prefix=service.prefix_sms,
        )
        created_at = notification.created_at
        key_type = notification.key_type
        if service.research_mode or notification.key_type == KEY_TYPE_TEST:
            update_notification_to_sending(notification, provider)
            send_sms_response(provider.get_name(), str(notification.id), notification.to)

        else:
            try:
                provider.send_sms(
                    to=notification.normalised_to,
                    content=str(template),
                    reference=str(notification.id),
                    sender=notification.reply_to_text
                )
            except Exception as e:
                notification.billable_units = template.fragment_count
                dao_update_notification(notification)
                dao_reduce_sms_provider_priority(provider.get_name(), time_threshold=timedelta(minutes=1))
                raise e
            else:
                notification.billable_units = template.fragment_count
                update_notification_to_sending(notification, provider)

        delta_seconds = (datetime.utcnow() - created_at).total_seconds()
        statsd_client.timing("sms.total-time", delta_seconds)

        if key_type == KEY_TYPE_TEST:
            statsd_client.timing("sms.test-key.total-time", delta_seconds)
        else:
            statsd_client.timing("sms.live-key.total-time", delta_seconds)
            if str(service.id) in current_app.config.get('HIGH_VOLUME_SERVICE'):
                statsd_client.timing("sms.live-key.high-volume.total-time", delta_seconds)
            else:
                statsd_client.timing("sms.live-key.not-high-volume.total-time", delta_seconds)


def send_email_to_provider(notification):
    service = SerialisedService.from_id(notification.service_id)

    if not service.active:
        technical_failure(notification=notification)
        return
    if notification.status == 'created':
        provider = provider_to_use(EMAIL_TYPE)

        template_dict = SerialisedTemplate.from_id_and_service_id(
            template_id=notification.template_id, service_id=service.id, version=notification.template_version
        ).__dict__

        html_email = HTMLEmailTemplate(
            template_dict,
            values=notification.personalisation,
            **get_html_email_options(service)
        )

        plain_text_email = PlainTextEmailTemplate(
            template_dict,
            values=notification.personalisation
        )
        created_at = notification.created_at
        key_type = notification.key_type
        if service.research_mode or notification.key_type == KEY_TYPE_TEST:
            notification.reference = str(create_uuid())
            update_notification_to_sending(notification, provider)
            send_email_response(notification.reference, notification.to)
        else:
            from_address = '"{}" <{}@{}>'.format(service.name, service.email_from,
                                                 current_app.config['NOTIFY_EMAIL_DOMAIN'])

            reference = provider.send_email(
                from_address,
                notification.normalised_to,
                plain_text_email.subject,
                body=str(plain_text_email),
                html_body=str(html_email),
                reply_to_address=notification.reply_to_text
            )
            notification.reference = reference
            update_notification_to_sending(notification, provider)
        delta_seconds = (datetime.utcnow() - created_at).total_seconds()

        if key_type == KEY_TYPE_TEST:
            statsd_client.timing("email.test-key.total-time", delta_seconds)
        else:
            statsd_client.timing("email.live-key.total-time", delta_seconds)
            if str(service.id) in current_app.config.get('HIGH_VOLUME_SERVICE'):
                statsd_client.timing("email.live-key.high-volume.total-time", delta_seconds)
            else:
                statsd_client.timing("email.live-key.not-high-volume.total-time", delta_seconds)


def update_notification_to_sending(notification, provider):
    notification.sent_at = datetime.utcnow()
    notification.sent_by = provider.get_name()
    if notification.status not in NOTIFICATION_STATUS_TYPES_COMPLETED:
        notification.status = NOTIFICATION_SENT if notification.international else NOTIFICATION_SENDING
    dao_update_notification(notification)


provider_cache = TTLCache(maxsize=8, ttl=10)


@cached(cache=provider_cache)
def provider_to_use(notification_type, international=False):
    active_providers = [
        p for p in get_provider_details_by_notification_type(notification_type, international) if p.active
    ]

    if not active_providers:
        current_app.logger.error(
            "{} failed as no active providers".format(notification_type)
        )
        raise Exception("No active {} providers".format(notification_type))

    chosen_provider = random.choices(active_providers, weights=[p.priority for p in active_providers])[0]

    return notification_provider_clients.get_client_by_name_and_type(chosen_provider.identifier, notification_type)


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
    if isinstance(service, SerialisedService):
        branding = dao_get_email_branding_by_id(service.email_branding)
    else:
        branding = service.email_branding

    logo_url = get_logo_url(
        current_app.config['ADMIN_BASE_URL'],
        branding.logo
    ) if branding.logo else None

    return {
        'govuk_banner': branding.brand_type == BRANDING_BOTH,
        'brand_banner': branding.brand_type == BRANDING_ORG_BANNER,
        'brand_colour': branding.colour,
        'brand_logo': logo_url,
        'brand_text': branding.text,
        'brand_name': branding.name,
    }


def technical_failure(notification):
    notification.status = NOTIFICATION_TECHNICAL_FAILURE
    dao_update_notification(notification)
    raise NotificationTechnicalFailureException(
        "Send {} for notification id {} to provider is not allowed: service {} is inactive".format(
            notification.notification_type,
            notification.id,
            notification.service_id))
