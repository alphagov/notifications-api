from datetime import datetime, timedelta

from flask import url_for
from app.models import SMS_TYPE, EMAIL_TYPE
from notifications_utils.template import SMSMessageTemplate, PlainTextEmailTemplate


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


def url_with_token(data, url, config):
    from notifications_utils.url_safe_token import generate_token
    token = generate_token(data, config['SECRET_KEY'], config['DANGEROUS_SALT'])
    base_url = config['ADMIN_BASE_URL'] + url
    return base_url + token


def get_template_instance(template, values):
    return {
        SMS_TYPE: SMSMessageTemplate, EMAIL_TYPE: PlainTextEmailTemplate
    }[template['template_type']](template, values)


def get_midnight_for_date(date):
    midnight = datetime.combine(date, datetime.min.time())
    return midnight


def get_midnight_for_day_before(date):
    day_before = date - timedelta(1)
    return get_midnight_for_date(day_before)
