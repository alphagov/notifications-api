from datetime import datetime, timedelta

import pytz
from flask import url_for
from sqlalchemy import func
from notifications_utils.template import SMSMessageTemplate, WithSubjectTemplate, get_html_email_body
from notifications_utils.timezones import convert_utc_to_bst

local_timezone = pytz.timezone("Europe/London")


def pagination_links(pagination, endpoint, **kwargs):
    if 'page' in kwargs:
        kwargs.pop('page', None)
    links = {}
    if pagination.has_prev:
        links['prev'] = url_for(endpoint, page=pagination.prev_num, **kwargs)
    if pagination.has_next:
        links['next'] = url_for(endpoint, page=pagination.next_num, **kwargs)
        links['last'] = url_for(endpoint, page=pagination.pages, **kwargs)
    return links


def url_with_token(data, url, config, base_url=None):
    from notifications_utils.url_safe_token import generate_token
    token = generate_token(data, config['SECRET_KEY'], config['DANGEROUS_SALT'])
    base_url = (base_url or config['ADMIN_BASE_URL']) + url
    return base_url + token


def get_template_instance(template, values):
    from app.models import SMS_TYPE, EMAIL_TYPE, LETTER_TYPE
    return {
        SMS_TYPE: SMSMessageTemplate, EMAIL_TYPE: WithSubjectTemplate, LETTER_TYPE: WithSubjectTemplate
    }[template['template_type']](template, values)


def get_html_email_body_from_template(template_instance):
    from app.models import EMAIL_TYPE

    if template_instance.template_type != EMAIL_TYPE:
        return None

    return get_html_email_body(
        template_instance.content,
        template_instance.values,
    )


def get_london_midnight_in_utc(date):
    """
     This function converts date to midnight as BST (British Standard Time) to UTC,
     the tzinfo is lastly removed from the datetime because the database stores the timestamps without timezone.
     :param date: the day to calculate the London midnight in UTC for
     :return: the datetime of London midnight in UTC, for example 2016-06-17 = 2016-06-16 23:00:00
    """
    return local_timezone.localize(datetime.combine(date, datetime.min.time())).astimezone(
        pytz.UTC).replace(
        tzinfo=None)


def get_midnight_for_day_before(date):
    day_before = date - timedelta(1)
    return get_london_midnight_in_utc(day_before)


def get_london_month_from_utc_column(column):
    """
     Where queries need to count notifications by month it needs to be
     the month in BST (British Summer Time).
     The database stores all timestamps as UTC without the timezone.
      - First set the timezone on created_at to UTC
      - then convert the timezone to BST (or Europe/London)
      - lastly truncate the datetime to month with which we can group
        queries
    """
    return func.date_trunc(
        "month",
        func.timezone("Europe/London", func.timezone("UTC", column))
    )


def get_public_notify_type_text(notify_type, plural=False):
    from app.models import (SMS_TYPE, UPLOAD_DOCUMENT, PRECOMPILED_LETTER)
    notify_type_text = notify_type
    if notify_type == SMS_TYPE:
        notify_type_text = 'text message'
    if notify_type == UPLOAD_DOCUMENT:
        notify_type_text = 'document'
    if notify_type == PRECOMPILED_LETTER:
        notify_type_text = 'precompiled letter'

    return '{}{}'.format(notify_type_text, 's' if plural else '')


def midnight_n_days_ago(number_of_days):
    """
    Returns midnight a number of days ago. Takes care of daylight savings etc.
    """
    return get_london_midnight_in_utc(datetime.utcnow() - timedelta(days=number_of_days))


def last_n_days(limit_days):
    """
    Returns the last n dates, oldest first. Takes care of daylight savings (but returns a date, be careful how you
    manipulate it later! Don't directly use the date for comparing to UTC datetimes!). Includes today.
    """
    return [
        datetime.combine(
            (convert_utc_to_bst(datetime.utcnow()) - timedelta(days=x)),
            datetime.min.time()
        )
        # reverse the countdown, -1 from first two args to ensure it stays 0-indexed
        for x in range(limit_days - 1, -1, -1)
    ]


def escape_special_characters(string):
    for special_character in ('\\', '_', '%', '/'):
        string = string.replace(
            special_character,
            r'\{}'.format(special_character)
        )
    return string
