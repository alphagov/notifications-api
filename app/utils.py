from datetime import datetime, timedelta

import pytz
from flask import current_app, url_for
from sqlalchemy import func
from notifications_utils.template import SMSMessageTemplate, PlainTextEmailTemplate, LetterPreviewTemplate

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


def url_with_token(data, url, config):
    from notifications_utils.url_safe_token import generate_token
    token = generate_token(data, config['SECRET_KEY'], config['DANGEROUS_SALT'])
    base_url = config['ADMIN_BASE_URL'] + url
    return base_url + token


def get_template_instance(template, values):
    from app.models import SMS_TYPE, EMAIL_TYPE, LETTER_TYPE
    return {
        SMS_TYPE: SMSMessageTemplate, EMAIL_TYPE: PlainTextEmailTemplate, LETTER_TYPE: PlainTextEmailTemplate
    }[template['template_type']](template, values)


def get_london_midnight_in_utc(date):
    """
     This function converts date to midnight as BST (British Standard Time) to UTC,
     the tzinfo is lastly removed from the datetime because the database stores the timestamps without timezone.
     :param date: the day to calculate the London midnight in UTC for
     :return: the datetime of London midnight in UTC, for example 2016-06-17 = 2016-06-17 23:00:00
    """
    return local_timezone.localize(datetime.combine(date, datetime.min.time())).astimezone(
        pytz.UTC).replace(
        tzinfo=None)


def get_midnight_for_day_before(date):
    day_before = date - timedelta(1)
    return get_london_midnight_in_utc(day_before)


def convert_utc_to_bst(utc_dt):
    return pytz.utc.localize(utc_dt).astimezone(local_timezone).replace(tzinfo=None)


def convert_bst_to_utc(date):
    return local_timezone.localize(date).astimezone(pytz.UTC).replace(tzinfo=None)


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


def cache_key_for_service_template_counter(service_id, limit_days=7):
    return "{}-template-counter-limit-{}-days".format(service_id, limit_days)


def get_public_notify_type_text(notify_type, plural=False):
    from app.models import SMS_TYPE
    notify_type_text = notify_type
    if notify_type == SMS_TYPE:
        notify_type_text = 'text message'

    return '{}{}'.format(notify_type_text, 's' if plural else '')


def get_unrestricted_letter_ids(job_ids):
    from app.dao.jobs_dao import (
        dao_get_job_by_id,
        dao_update_job
    )

    from app.models import (LETTER_TYPE, JOB_STATUS_ERROR)
    from app.dao.templates_dao import dao_get_template_by_id

    unrestricted_job_ids = []

    for job_id in job_ids:
        job = dao_get_job_by_id(job_id)

        template = dao_get_template_by_id(job.template_id, job.template_version)

        if template.template_type == LETTER_TYPE:
            if job.service.restricted:
                job.job_status = JOB_STATUS_ERROR
                dao_update_job(job)
                current_app.logger.warn(
                    "Job {} has been set to error, service {} is in trial mode".format(job.id, job.service.id))
            else:
                unrestricted_job_ids.append(job_id)

    return unrestricted_job_ids
