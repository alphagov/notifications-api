from datetime import datetime

from flask import current_app

from app.utils import get_midnight_for_day_before, get_london_midnight_in_utc
from app.dao.notifications_dao import dao_get_total_notifications_sent_per_day_for_performance_platform
from app import performance_platform_client


def send_processing_time_to_performance_platform():
    today = datetime.utcnow()
    start_date = get_midnight_for_day_before(today)
    end_date = get_london_midnight_in_utc(today)

    send_processing_time_for_start_and_end(start_date, end_date)


def send_processing_time_for_start_and_end(start_date, end_date):
    result = dao_get_total_notifications_sent_per_day_for_performance_platform(start_date, end_date)

    current_app.logger.info(
        'Sending processing-time to performance platform for date {}. Total: {}, under 10 secs {}'.format(
            start_date, result.messages_total, result.messages_within_10_secs
        )
    )

    send_processing_time_data(start_date, 'messages-total', result.messages_total)
    send_processing_time_data(start_date, 'messages-within-10-secs', result.messages_within_10_secs)


def send_processing_time_data(date, status, count):
    payload = performance_platform_client.format_payload(
        dataset='processing-time',
        date=date,
        group_name='status',
        group_value=status,
        count=count
    )

    performance_platform_client.send_stats_to_performance_platform(payload)
