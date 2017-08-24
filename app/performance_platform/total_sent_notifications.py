from datetime import datetime

from app import performance_platform_client
from app.dao.notifications_dao import get_total_sent_notifications_in_date_range
from app.utils import (
    get_london_midnight_in_utc,
    get_midnight_for_day_before,
    convert_utc_to_bst,
)


def send_total_notifications_sent_for_day_stats(date, channel, count, period):
    payload = {
        '_timestamp': convert_utc_to_bst(date).isoformat(),
        'service': 'govuk-notify',
        'channel': channel,
        'count': count,
        'dataType': 'notifications',
        'period': period
    }
    performance_platform_client.add_id_to_payload(payload)

    performance_platform_client.send_stats_to_performance_platform(
        dataset='notifications',
        payload=payload
    )


def get_total_sent_notifications_yesterday():
    today = datetime.utcnow()
    start_date = get_midnight_for_day_before(today)
    end_date = get_london_midnight_in_utc(today)

    email_count = get_total_sent_notifications_in_date_range(start_date, end_date, 'email')
    sms_count = get_total_sent_notifications_in_date_range(start_date, end_date, 'sms')

    return {
        "start_date": start_date,
        "email": {
            "count": email_count
        },
        "sms": {
            "count": sms_count
        }
    }
