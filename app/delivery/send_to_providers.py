import random
from datetime import datetime, timedelta
from urllib import parse

from flask import current_app
from notifications_utils.template import (
    HTMLEmailTemplate,
    PlainTextEmailTemplate,
    SMSMessageTemplate,
)

from app import create_uuid, db, notification_provider_clients, redis_store, statsd_client
from app.celery.research_mode_tasks import (
    send_email_response,
    send_sms_response,
)
from app.constants import (
    BRANDING_BOTH,
    BRANDING_ORG_BANNER,
    EMAIL_TYPE,
    KEY_TYPE_TEST,
    NOTIFICATION_SENDING,
    NOTIFICATION_SENT,
    NOTIFICATION_STATUS_TYPES_COMPLETED,
    NOTIFICATION_TECHNICAL_FAILURE,
    SMS_PROVIDER_ERROR_INTERVAL,
    SMS_PROVIDER_ERROR_THRESHOLD,
    SMS_TYPE,
)
from app.dao.email_branding_dao import dao_get_email_branding_by_id
from app.dao.notifications_dao import dao_update_notification
from app.dao.provider_details_dao import (
    dao_reduce_sms_provider_priority,
)
from app.exceptions import NotificationTechnicalFailureException
from app.models import Notification
from app.provider_selection import get_allowed_providers
from app.serialised_models import SerialisedProviders, SerialisedService, SerialisedTemplate


def send_sms_to_provider(notification: Notification) -> None:
    service = SerialisedService.from_id(notification.service_id)

    if not service.active:
        technical_failure(notification=notification)
        return

    if notification.status == "created":
        provider = provider_to_use(
            SMS_TYPE, notification.international, provider_requested=notification.provider_requested
        )

        template_model = SerialisedTemplate.from_id_service_id_and_version(
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
        if notification.key_type == KEY_TYPE_TEST:
            update_notification_to_sending(notification, provider)
            send_sms_response(provider.name, str(notification.id), notification.to)

        else:
            try:
                # End DB session here so that we don't have a connection stuck open waiting on the call
                # to one of the SMS providers
                # We don't want to tie our DB connections being open to the performance of our SMS
                # providers as a slow down of our providers can cause us to run out of DB connections
                # Therefore we pull all the data from our DB models into `send_sms_kwargs`now before
                # closing the session (as otherwise it would be reopened immediately)
                send_sms_kwargs = {
                    "to": notification.normalised_to,
                    "content": str(template),
                    "reference": str(notification.id),
                    "sender": notification.reply_to_text,
                    "international": notification.international,
                }
                db.session.close()  # no commit needed as no changes to objects have been made above
                provider.send_sms(**send_sms_kwargs)
            except Exception as e:
                notification.billable_units = template.fragment_count
                dao_update_notification(notification)

                if redis_store.exceeded_rate_limit(
                    f"{provider.name}-error-rate", SMS_PROVIDER_ERROR_THRESHOLD, SMS_PROVIDER_ERROR_INTERVAL
                ):
                    dao_reduce_sms_provider_priority(provider.name, time_threshold=timedelta(minutes=1))
                    current_app.logger.warning(
                        "Error threshold exceeded for provider %s",
                        provider.name,
                        extra={"provider_name": provider.name},
                    )
                raise e
            else:
                notification.billable_units = template.fragment_count
                update_notification_to_sending(notification, provider)
                if notification.international:
                    statsd_client.incr(f"international-sms.{NOTIFICATION_SENT}.{notification.phone_prefix}")

        delta_seconds = (datetime.utcnow() - created_at).total_seconds()
        statsd_client.timing("sms.total-time", delta_seconds)

        if key_type == KEY_TYPE_TEST:
            statsd_client.timing("sms.test-key.total-time", delta_seconds)
        else:
            statsd_client.timing("sms.live-key.total-time", delta_seconds)
    else:
        extra = {"notification_id": notification.id, "notification_status": notification.status}
        current_app.logger.warning(
            "Not sending SMS notification %(notification_id)s because status "
            "is %(notification_status)r (not 'created')",
            extra,
            extra=extra,
        )


def _get_email_headers(notification: Notification, template: SerialisedTemplate) -> list[dict[str, str]]:
    if unsubscribe_link := notification.get_unsubscribe_link_for_headers(
        template_has_unsubscribe_link=template.has_unsubscribe_link
    ):
        return [
            {"Name": "List-Unsubscribe", "Value": f"<{unsubscribe_link}>"},
            {"Name": "List-Unsubscribe-Post", "Value": "List-Unsubscribe=One-Click"},
        ]

    return []


def send_email_to_provider(notification):
    service = SerialisedService.from_id(notification.service_id)

    if not service.active:
        technical_failure(notification=notification)
        return
    if notification.status == "created":
        provider = provider_to_use(EMAIL_TYPE, provider_requested=notification.provider_requested)

        template = SerialisedTemplate.from_id_service_id_and_version(
            template_id=notification.template_id, service_id=service.id, version=notification.template_version
        )

        unsubscribe_link_for_body = notification.get_unsubscribe_link_for_body(
            template_has_unsubscribe_link=template.has_unsubscribe_link
        )

        html_email = HTMLEmailTemplate(
            template.__dict__,
            values=notification.personalisation,
            unsubscribe_link=unsubscribe_link_for_body,
            **get_html_email_options(service),
        )

        plain_text_email = PlainTextEmailTemplate(
            template.__dict__,
            values=notification.personalisation,
            unsubscribe_link=unsubscribe_link_for_body,
        )
        created_at = notification.created_at
        key_type = notification.key_type
        if notification.key_type == KEY_TYPE_TEST:
            notification.reference = str(create_uuid())
            update_notification_to_sending(notification, provider)
            send_email_response(notification.reference, notification.to)
        else:
            email_sender_name = service.custom_email_sender_name or service.name
            from_address = (
                f'"{email_sender_name}" <{service.email_sender_local_part}@{current_app.config["NOTIFY_EMAIL_DOMAIN"]}>'
            )

            reference = provider.send_email(
                from_address=from_address,
                to_address=notification.normalised_to,
                subject=plain_text_email.subject,
                body=str(plain_text_email),
                html_body=str(html_email),
                reply_to_address=notification.reply_to_text,
                headers=_get_email_headers(notification, template),
            )
            notification.reference = reference
            update_notification_to_sending(notification, provider)
        delta_seconds = (datetime.utcnow() - created_at).total_seconds()

        if key_type == KEY_TYPE_TEST:
            statsd_client.timing("email.test-key.total-time", delta_seconds)
        else:
            statsd_client.timing("email.live-key.total-time", delta_seconds)


def update_notification_to_sending(notification, provider):
    notification.sent_at = datetime.utcnow()
    notification.sent_by = provider.name
    if notification.status not in NOTIFICATION_STATUS_TYPES_COMPLETED:
        notification.status = NOTIFICATION_SENT if notification.international else NOTIFICATION_SENDING
    dao_update_notification(notification)


def provider_to_use(notification_type, international=False, provider_requested=None):
    # If a provider was explicitly requested, enforce availability and configuration.
    if provider_requested:
        allowed = get_allowed_providers(notification_type, international=international)
        if provider_requested not in allowed:
            current_app.logger.error(
                "Requested provider %s is not available for %s notifications",
                provider_requested,
                notification_type,
                extra={"notification_type": notification_type, "provider_requested": provider_requested},
            )
            raise Exception(f"Requested provider {provider_requested} is not available for {notification_type}")

        provider = notification_provider_clients.get_client_by_name_and_type(provider_requested, notification_type)
        if not provider:
            current_app.logger.error(
                "Requested provider %s is not configured for %s notifications",
                provider_requested,
                notification_type,
                extra={"notification_type": notification_type, "provider_requested": provider_requested},
            )
            raise Exception(f"Requested provider {provider_requested} is not configured for {notification_type}")

        return provider

    active_providers = [
        p for p in SerialisedProviders.from_notification_type(notification_type, international) if p.active
    ]

    if not active_providers:
        current_app.logger.error(
            "%s notification failed as no active providers",
            notification_type,
            extra={"notification_type": notification_type},
        )
        raise Exception(f"No active {notification_type} providers")

    if len(active_providers) == 1:
        weights = [100]
    else:
        weights = [p.priority for p in active_providers]

    chosen_provider = random.choices(active_providers, weights=weights)[0]

    return notification_provider_clients.get_client_by_name_and_type(chosen_provider.identifier, notification_type)


def get_logo_url(base_url, logo_file):
    base_url = parse.urlparse(base_url)
    netloc = base_url.netloc

    if base_url.hostname.split(".")[-1] == "localhost":
        netloc = "notify.tools"
    elif base_url.netloc.startswith("www"):
        # strip "www."
        netloc = base_url.netloc[4:]

    logo_url = parse.ParseResult(
        scheme=base_url.scheme,
        netloc="static-logos." + netloc,
        path=logo_file,
        params=base_url.params,
        query=base_url.query,
        fragment=base_url.fragment,
    )
    return parse.urlunparse(logo_url)


def get_html_email_options(service):
    if service.email_branding is None:
        return {
            "govuk_banner": True,
            "brand_banner": False,
            "rebrand": True,
        }
    if isinstance(service, SerialisedService):
        branding = dao_get_email_branding_by_id(service.email_branding)
    else:
        branding = service.email_branding

    logo_url = get_logo_url(current_app.config["ADMIN_BASE_URL"], branding.logo) if branding.logo else None

    return {
        "govuk_banner": branding.brand_type == BRANDING_BOTH,
        "brand_banner": branding.brand_type == BRANDING_ORG_BANNER,
        "brand_colour": branding.colour,
        "brand_logo": logo_url,
        "brand_text": branding.text,
        "brand_alt_text": branding.alt_text,
        "rebrand": True,
    }


def technical_failure(notification):
    notification.status = NOTIFICATION_TECHNICAL_FAILURE
    dao_update_notification(notification)
    raise NotificationTechnicalFailureException(
        f"Send {notification.notification_type} for notification id {notification.id} to provider "
        f"is not allowed: service {notification.service_id} is inactive"
    )
