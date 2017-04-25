from flask import current_app
from notifications_utils.recipients import validate_and_format_phone_number, validate_and_format_email_address

from app.dao import services_dao
from app.models import KEY_TYPE_TEST, KEY_TYPE_TEAM, SMS_TYPE
from app.service.utils import service_allowed_to_send_to
from app.v2.errors import TooManyRequestsError, BadRequestError, RateLimitError
from app import redis_store
from notifications_utils.clients import redis


def check_service_over_api_rate_limit(service, api_key):
    if current_app.config['API_RATE_LIMIT_ENABLED']:
        cache_key = redis.rate_limit_cache_key(service.id, api_key.key_type)
        rate_limit = current_app.config['API_KEY_LIMITS'][api_key.key_type]['limit']
        interval = current_app.config['API_KEY_LIMITS'][api_key.key_type]['interval']
        if redis_store.exceeded_rate_limit(
                cache_key,
                rate_limit,
                interval):
            raise RateLimitError(
                rate_limit,
                interval,
                api_key.key_type)


def check_service_over_daily_message_limit(key_type, service):
    if key_type != KEY_TYPE_TEST:
        cache_key = redis.daily_limit_cache_key(service.id)
        service_stats = redis_store.get(cache_key)
        if not service_stats:
            service_stats = services_dao.fetch_todays_total_message_count(service.id)
            redis_store.set(cache_key, service_stats, ex=3600)
        if int(service_stats) >= service.message_limit:
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


def service_can_send_to_recipient(send_to, key_type, service):
    if not service_allowed_to_send_to(send_to, service, key_type):
        if key_type == KEY_TYPE_TEAM:
            message = 'Can’t send to this recipient using a team-only API key'
        else:
            message = (
                'Can’t send to this recipient when service is in trial mode '
                '– see https://www.notifications.service.gov.uk/trial-mode'
            )
        raise BadRequestError(message=message)


def validate_and_format_recipient(send_to, key_type, service, notification_type):
    service_can_send_to_recipient(send_to, key_type, service)
    if notification_type == SMS_TYPE:
        return validate_and_format_phone_number(number=send_to)
    else:
        return validate_and_format_email_address(email_address=send_to)


def check_sms_content_char_count(content_count):
    char_count_limit = current_app.config.get('SMS_CHAR_COUNT_LIMIT')
    if content_count > char_count_limit:
        message = 'Content for template has a character count greater than the limit of {}'.format(char_count_limit)
        raise BadRequestError(message=message)
