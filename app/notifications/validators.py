from sqlalchemy.orm.exc import NoResultFound
from flask import current_app
from notifications_utils import SMS_CHAR_COUNT_LIMIT
from notifications_utils.recipients import (
    validate_and_format_phone_number,
    validate_and_format_email_address,
    get_international_phone_info
)
from notifications_utils.clients.redis import rate_limit_cache_key, daily_limit_cache_key

from app.dao import services_dao, templates_dao
from app.dao.service_sms_sender_dao import dao_get_service_sms_senders_by_id
from app.models import (
    INTERNATIONAL_SMS_TYPE, SMS_TYPE, EMAIL_TYPE, LETTER_TYPE,
    KEY_TYPE_TEST, KEY_TYPE_TEAM, SCHEDULE_NOTIFICATIONS
)
from app.service.utils import service_allowed_to_send_to
from app.v2.errors import TooManyRequestsError, BadRequestError, RateLimitError
from app import redis_store
from app.notifications.process_notifications import create_content_for_notification
from app.utils import get_public_notify_type_text
from app.dao.service_email_reply_to_dao import dao_get_reply_to_by_id
from app.dao.service_letter_contact_dao import dao_get_letter_contact_by_id


def check_service_over_api_rate_limit(service, api_key):
    if current_app.config['API_RATE_LIMIT_ENABLED'] and current_app.config['REDIS_ENABLED']:
        cache_key = rate_limit_cache_key(service.id, api_key.key_type)
        rate_limit = service.rate_limit
        interval = 60
        if redis_store.exceeded_rate_limit(cache_key, rate_limit, interval):
            current_app.logger.info("service {} has been rate limited for throughput".format(service.id))
            raise RateLimitError(rate_limit, interval, api_key.key_type)


def check_service_over_daily_message_limit(key_type, service):
    if key_type != KEY_TYPE_TEST and current_app.config['REDIS_ENABLED']:
        cache_key = daily_limit_cache_key(service.id)
        service_stats = redis_store.get(cache_key)
        if not service_stats:
            service_stats = services_dao.fetch_todays_total_message_count(service.id)
            redis_store.set(cache_key, service_stats, ex=3600)
        if int(service_stats) >= service.message_limit:
            current_app.logger.info(
                "service {} has been rate limited for daily use sent {} limit {}".format(
                    service.id, int(service_stats), service.message_limit)
            )
            raise TooManyRequestsError(service.message_limit)


def check_rate_limiting(service, api_key):
    check_service_over_api_rate_limit(service, api_key)
    check_service_over_daily_message_limit(api_key.key_type, service)


def check_template_is_for_notification_type(notification_type, template_type):
    if notification_type != template_type:
        message = "{0} template is not suitable for {1} notification".format(template_type,
                                                                             notification_type)
        raise BadRequestError(fields=[{'template': message}], message=message)


def check_template_is_active(template):
    if template.archived:
        raise BadRequestError(fields=[{'template': 'Template has been deleted'}],
                              message="Template has been deleted")


def service_can_send_to_recipient(send_to, key_type, service, allow_whitelisted_recipients=True):
    if not service_allowed_to_send_to(send_to, service, key_type, allow_whitelisted_recipients):
        if key_type == KEY_TYPE_TEAM:
            message = 'Can’t send to this recipient using a team-only API key'
        else:
            message = (
                'Can’t send to this recipient when service is in trial mode '
                '– see https://www.notifications.service.gov.uk/trial-mode'
            )
        raise BadRequestError(message=message)


def service_has_permission(notify_type, permissions):
    return notify_type in [p.permission for p in permissions]


def check_service_has_permission(notify_type, permissions):
    if not service_has_permission(notify_type, permissions):
        raise BadRequestError(message="Service is not allowed to send {}".format(
            get_public_notify_type_text(notify_type, plural=True)
        ))


def check_if_service_can_send_files_by_email(service_contact_link):
    if not service_contact_link:
        raise BadRequestError(
            message="Send files by email is not set up yet. Go to your settings page to manage send files by email"
        )


def check_service_can_schedule_notification(permissions, scheduled_for):
    if scheduled_for:
        if not service_has_permission(SCHEDULE_NOTIFICATIONS, permissions):
            raise BadRequestError(message="Cannot schedule notifications (this feature is invite-only)")


def validate_and_format_recipient(send_to, key_type, service, notification_type, allow_whitelisted_recipients=True):
    if send_to is None:
        raise BadRequestError(message="Recipient can't be empty")

    service_can_send_to_recipient(send_to, key_type, service, allow_whitelisted_recipients)

    if notification_type == SMS_TYPE:
        international_phone_info = get_international_phone_info(send_to)

        if international_phone_info.international and \
                INTERNATIONAL_SMS_TYPE not in [p.permission for p in service.permissions]:
            raise BadRequestError(message="Cannot send to international mobile numbers")

        return validate_and_format_phone_number(
            number=send_to,
            international=international_phone_info.international
        )
    elif notification_type == EMAIL_TYPE:
        return validate_and_format_email_address(email_address=send_to)


def check_sms_content_char_count(content_count):
    if content_count > SMS_CHAR_COUNT_LIMIT:
        message = 'Content for template has a character count greater than the limit of {}'.format(SMS_CHAR_COUNT_LIMIT)
        raise BadRequestError(message=message)


def check_notification_content_is_not_empty(template_with_content):
    if template_with_content.is_message_empty():
        message = 'Your message is empty.'
        raise BadRequestError(message=message)


def validate_template(template_id, personalisation, service, notification_type):
    try:
        template = templates_dao.dao_get_template_by_id_and_service_id(
            template_id=template_id,
            service_id=service.id
        )
    except NoResultFound:
        message = 'Template not found'
        raise BadRequestError(message=message,
                              fields=[{'template': message}])

    check_template_is_for_notification_type(notification_type, template.template_type)
    check_template_is_active(template)

    template_with_content = create_content_for_notification(template, personalisation)
    check_notification_content_is_not_empty(template_with_content)
    if template.template_type == SMS_TYPE:
        check_sms_content_char_count(template_with_content.content_count)

    return template, template_with_content


def check_reply_to(service_id, reply_to_id, type_):
    if type_ == EMAIL_TYPE:
        return check_service_email_reply_to_id(service_id, reply_to_id, type_)
    elif type_ == SMS_TYPE:
        return check_service_sms_sender_id(service_id, reply_to_id, type_)
    elif type_ == LETTER_TYPE:
        return check_service_letter_contact_id(service_id, reply_to_id, type_)


def check_service_email_reply_to_id(service_id, reply_to_id, notification_type):
    if reply_to_id:
        try:
            return dao_get_reply_to_by_id(service_id, reply_to_id).email_address
        except NoResultFound:
            message = 'email_reply_to_id {} does not exist in database for service id {}'\
                .format(reply_to_id, service_id)
            raise BadRequestError(message=message)


def check_service_sms_sender_id(service_id, sms_sender_id, notification_type):
    if sms_sender_id:
        try:
            return dao_get_service_sms_senders_by_id(service_id, sms_sender_id).sms_sender
        except NoResultFound:
            message = 'sms_sender_id {} does not exist in database for service id {}'\
                .format(sms_sender_id, service_id)
            raise BadRequestError(message=message)


def check_service_letter_contact_id(service_id, letter_contact_id, notification_type):
    if letter_contact_id:
        try:
            return dao_get_letter_contact_by_id(service_id, letter_contact_id).contact_block
        except NoResultFound:
            message = 'letter_contact_id {} does not exist in database for service id {}'\
                .format(letter_contact_id, service_id)
            raise BadRequestError(message=message)
